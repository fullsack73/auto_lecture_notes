from __future__ import annotations

import argparse
import difflib
import json
import platform
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Hashable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from lecture_auto.local_runtime import LocalRuntimeManager  # noqa: E402
from lecture_auto.model_manager import default_model_dir  # noqa: E402
from lecture_auto.stt_profiles import (  # noqa: E402
    LOCAL_STT_PROFILES,
    backend_evaluation_report,
    get_local_stt_profile,
    physical_cpu_count,
)
from lecture_auto.stt_refinement import audit_refinement  # noqa: E402
from lecture_auto.stt_quality import KOREAN_LECTURE_THRESHOLDS  # noqa: E402


AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".m4a", ".ogg")


@dataclass(frozen=True)
class BenchmarkPair:
    name: str
    audio_path: Path
    reference_path: Path


def discover_pairs(recordings_dir: Path) -> list[BenchmarkPair]:
    pairs: list[BenchmarkPair] = []
    for audio_path in sorted(recordings_dir.glob("test-*")):
        if audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        name = audio_path.stem.removeprefix("test-")
        reference_path = recordings_dir / f"transcript-{name}.md"
        if reference_path.is_file():
            pairs.append(
                BenchmarkPair(
                    name=name,
                    audio_path=audio_path.resolve(),
                    reference_path=reference_path.resolve(),
                )
            )
    return pairs


def normalize_words(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = re.sub(r"[^\w가-힣]+", " ", normalized, flags=re.UNICODE)
    return normalized.split()


def normalize_characters(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character)[0] in {"L", "N"}
    )


def edit_distance(reference: Sequence[Hashable], hypothesis: Sequence[Hashable]) -> int:
    """Return exact Levenshtein distance using a bit-parallel algorithm."""
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)
    if len(reference) > len(hypothesis):
        reference, hypothesis = hypothesis, reference

    character_masks: dict[Hashable, int] = {}
    for index, value in enumerate(reference):
        character_masks[value] = character_masks.get(value, 0) | (1 << index)

    positive = ~0
    negative = 0
    score = len(reference)
    highest_bit = 1 << (len(reference) - 1)

    for value in hypothesis:
        equal = character_masks.get(value, 0)
        combined = equal | negative
        horizontal = (((equal & positive) + positive) ^ positive) | equal
        positive_horizontal = negative | ~(horizontal | positive)
        negative_horizontal = positive & horizontal
        if positive_horizontal & highest_bit:
            score += 1
        elif negative_horizontal & highest_bit:
            score -= 1
        positive_horizontal = (positive_horizontal << 1) | 1
        negative_horizontal <<= 1
        positive = negative_horizontal | ~(combined | positive_horizontal)
        negative = positive_horizontal & combined

    return score


def error_rate(reference: Sequence[Hashable], hypothesis: Sequence[Hashable]) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return edit_distance(reference, hypothesis) / len(reference)


def omission_rate(reference: str, hypothesis: str) -> float:
    reference_values = normalize_words(reference)
    hypothesis_values = normalize_words(hypothesis)
    if not reference_values:
        return 0.0
    omitted = 0
    for operation, ref_start, ref_end, _hyp_start, _hyp_end in difflib.SequenceMatcher(
        None,
        reference_values,
        hypothesis_values,
        autojunk=False,
    ).get_opcodes():
        if operation in {"delete", "replace"}:
            omitted += ref_end - ref_start
    return omitted / len(reference_values)


def numeric_formula_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text)
    return re.findall(
        r"(?<!\w)(?:[+-]?\d+(?:[.,:/-]\d+)*(?:%|[A-Za-z]+)?|"
        r"[A-Za-z]\s*[=<>±]\s*[^\s,.;]+)",
        normalized,
    )


def candidate_terms(text: str) -> list[str]:
    values = re.findall(
        r"\b(?:[A-Z][A-Za-z0-9+.#-]{1,}|[A-Z]{2,}(?:-[A-Z0-9]+)*)\b",
        text,
    )
    return list(dict.fromkeys(values))


def token_recall(expected: Sequence[str], hypothesis: str) -> float | None:
    if not expected:
        return None
    normalized_hypothesis = unicodedata.normalize("NFKC", hypothesis).casefold()
    found = sum(
        unicodedata.normalize("NFKC", value).casefold() in normalized_hypothesis
        for value in expected
    )
    return found / len(expected)


def evaluate_text(
    reference: str,
    hypothesis: str,
    *,
    glossary: Sequence[str] = (),
) -> dict[str, object]:
    reference_characters = normalize_characters(reference)
    hypothesis_characters = normalize_characters(hypothesis)
    reference_words = normalize_words(reference)
    hypothesis_words = normalize_words(hypothesis)
    expected_terms = list(dict.fromkeys([*glossary, *candidate_terms(reference)]))
    expected_numeric = numeric_formula_tokens(reference)
    return {
        "cer": error_rate(reference_characters, hypothesis_characters),
        "wer": error_rate(reference_words, hypothesis_words),
        "omission_rate": omission_rate(reference, hypothesis),
        "term_recall": token_recall(expected_terms, hypothesis),
        "numeric_formula_recall": token_recall(expected_numeric, hypothesis),
        "reference_term_count": len(expected_terms),
        "reference_numeric_formula_count": len(expected_numeric),
        "reference_character_count": len(reference_characters),
        "hypothesis_character_count": len(hypothesis_characters),
        "reference_word_count": len(reference_words),
        "hypothesis_word_count": len(hypothesis_words),
        "hypothesis_to_reference_character_ratio": (
            len(hypothesis_characters) / len(reference_characters)
            if reference_characters
            else None
        ),
        "repetition": repetition_summary(hypothesis_words),
    }


def confidence_summary(segments: list[dict[str, object]]) -> dict[str, object]:
    logprobs = [
        float(segment["avg_logprob"])
        for segment in segments
        if segment.get("avg_logprob") is not None
    ]
    compression_ratios = [
        float(segment["compression_ratio"])
        for segment in segments
        if segment.get("compression_ratio") is not None
    ]
    no_speech_probs = [
        float(segment["no_speech_prob"])
        for segment in segments
        if segment.get("no_speech_prob") is not None
    ]
    return {
        "segment_count": len(segments),
        "mean_avg_logprob": mean(logprobs) if logprobs else None,
        "low_logprob_segment_count": sum(
            value < KOREAN_LECTURE_THRESHOLDS["avg_logprob"]
            for value in logprobs
        ),
        "high_compression_segment_count": sum(
            value > KOREAN_LECTURE_THRESHOLDS["compression_ratio"]
            for value in compression_ratios
        ),
        "high_no_speech_segment_count": sum(
            value > KOREAN_LECTURE_THRESHOLDS["no_speech_probability"]
            for value in no_speech_probs
        ),
    }


def merge_segment_payloads(
    primary: list[dict[str, object]],
    retry: list[dict[str, object]],
    windows: Sequence[Sequence[float]],
) -> list[dict[str, object]]:
    if not retry or not windows:
        return primary

    def inside(segment: dict[str, object]) -> bool:
        midpoint = (
            float(segment.get("start_time") or 0)
            + float(segment.get("end_time") or 0)
        ) / 2
        return any(float(window[0]) <= midpoint <= float(window[1]) for window in windows)

    merged = [segment for segment in primary if not inside(segment)]
    merged.extend(segment for segment in retry if inside(segment))
    return sorted(
        merged,
        key=lambda value: (
            float(value.get("start_time") or 0),
            float(value.get("end_time") or 0),
        ),
    )


def repetition_summary(words: Sequence[str]) -> dict[str, int | float]:
    if not words:
        return {
            "max_consecutive_token_run": 0,
            "repeated_token_excess": 0,
            "immediate_repeated_ngram_count": 0,
            "unique_word_ratio": 0.0,
        }

    max_run = 1
    current_run = 1
    repeated_token_excess = 0
    for previous, current in zip(words, words[1:]):
        if current == previous:
            current_run += 1
            max_run = max(max_run, current_run)
            if current_run > 3:
                repeated_token_excess += 1
        else:
            current_run = 1

    repeated_ngram_positions: set[int] = set()
    for size in range(2, 6):
        for end in range(size * 2, len(words) + 1):
            if words[end - size * 2 : end - size] == words[end - size : end]:
                repeated_ngram_positions.add(end - size)

    return {
        "max_consecutive_token_run": max_run,
        "repeated_token_excess": repeated_token_excess,
        "immediate_repeated_ngram_count": len(repeated_ngram_positions),
        "unique_word_ratio": len(set(words)) / len(words),
    }


def profile_options(name: str) -> dict[str, object]:
    if name in LOCAL_STT_PROFILES:
        profile = get_local_stt_profile(name)
        return {
            key: value
            for key, value in profile.to_dict().items()
            if key not in {"name", "model"}
        }
    if name == "optimized":
        return {
            "device": "auto",
            "compute_type": "auto",
            "batch_size": 4,
            "beam_size": 1,
            "temperature": 0.0,
            "vad_filter": True,
            "vad_min_silence_duration_ms": 1000,
            "condition_on_previous_text": False,
            "word_timestamps": False,
            "cpu_threads": 0,
            "num_workers": 1,
        }
    return {
        "device": "cpu",
        "compute_type": "int8",
        "batch_size": 1,
        "beam_size": 5,
        "temperature": None,
        "vad_filter": False,
        "vad_min_silence_duration_ms": 2000,
        "condition_on_previous_text": True,
        "word_timestamps": False,
        "cpu_threads": 0,
        "num_workers": 1,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark local faster-whisper against paired lecture transcripts."
    )
    parser.add_argument(
        "--recordings-dir",
        type=Path,
        default=REPOSITORY_ROOT / "recordings",
    )
    parser.add_argument("--pair", action="append", dest="pairs")
    parser.add_argument(
        "--profile",
        choices=("baseline", "optimized", *LOCAL_STT_PROFILES),
        default="baseline",
    )
    parser.add_argument("--model")
    parser.add_argument("--language", default="ko")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--compute-type")
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--beam-size", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument(
        "--vad-filter",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--vad-min-silence-ms", type=int)
    parser.add_argument(
        "--condition-on-previous-text",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--word-timestamps",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--hotwords")
    parser.add_argument("--cpu-threads", type=int)
    parser.add_argument("--num-workers", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Repeated runs in one warm worker; use at least 2 for cold/warm timing.",
    )
    parser.add_argument(
        "--glossary-file",
        type=Path,
        help="Optional newline-delimited expected technical/proper-name terms.",
    )
    parser.add_argument(
        "--refined-dir",
        type=Path,
        help="Optional directory containing refined-PAIR.md files for safety evaluation.",
    )
    parser.add_argument(
        "--quality-retry",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="Print machine-readable local STT profiles and exit.",
    )
    parser.add_argument(
        "--list-backends",
        action="store_true",
        help="Print backend/model packaging evaluations and exit.",
    )
    parser.add_argument(
        "--audio-preflight",
        action="store_true",
        help="Decode each input once to measure volume, clipping, and silence.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Write audio diagnostics without running transcription.",
    )
    return parser


def resolve_options(args: argparse.Namespace) -> dict[str, object]:
    options = profile_options(args.profile)
    overrides = {
        "device": args.device,
        "compute_type": args.compute_type,
        "batch_size": args.batch_size,
        "beam_size": args.beam_size,
        "temperature": args.temperature,
        "vad_filter": args.vad_filter,
        "vad_min_silence_duration_ms": args.vad_min_silence_ms,
        "condition_on_previous_text": args.condition_on_previous_text,
        "word_timestamps": args.word_timestamps,
        "hotwords": args.hotwords,
        "cpu_threads": args.cpu_threads,
        "num_workers": args.num_workers,
    }
    options.update({key: value for key, value in overrides.items() if value is not None})
    if int(options["batch_size"]) > 1 and not options["vad_filter"]:
        raise ValueError("batch_size > 1 requires --vad-filter")
    if args.runs < 1 or args.runs > 20:
        raise ValueError("--runs must be between 1 and 20")
    return options


def write_markdown(path: Path, report: dict[str, object]) -> None:
    lines = [
        "# Local STT benchmark",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Profile: `{report['profile']}`",
        f"- Model: `{report['model']}`",
        f"- Options: `{json.dumps(report['options'], ensure_ascii=False)}`",
        "",
        "| Pair | Audio min | Wall s | RTF | CER | WER | Omission | Term recall | Number recall | Segments |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in report["results"]:  # type: ignore[union-attr]
        if result.get("error"):
            lines.append(
                f"| {result['name']} | - | - | - | - | - | - | - | - | failed: "
                f"{str(result['error']).replace('|', '/')} |"
            )
            continue
        if "rtf" not in result:
            preflight = result.get("audio_preflight") or {}
            minutes = float(preflight.get("duration_seconds") or 0) / 60
            lines.append(
                f"| {result['name']} | {minutes:.2f} | - | - | - | - | - | - | - | "
                "preflight only |"
            )
            continue
        lines.append(
            "| {name} | {minutes:.2f} | {wall:.2f} | {rtf:.4f} | "
            "{cer:.4f} | {wer:.4f} | {omission:.4f} | {term} | {number} | {segments} |".format(
                name=result["name"],
                minutes=float(result["audio_duration_seconds"]) / 60,
                wall=float(result["wall_seconds"]),
                rtf=float(result["rtf"]),
                cer=float(result["cer"]),
                wer=float(result["wer"]),
                omission=float(result["omission_rate"]),
                term=(
                    f"{float(result['term_recall']):.4f}"
                    if result.get("term_recall") is not None
                    else "-"
                ),
                number=(
                    f"{float(result['numeric_formula_recall']):.4f}"
                    if result.get("numeric_formula_recall") is not None
                    else "-"
                ),
                segments=result["confidence"]["segment_count"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    if args.list_profiles:
        print(
            json.dumps(
                {
                    name: profile.to_dict()
                    for name, profile in LOCAL_STT_PROFILES.items()
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.list_backends:
        print(json.dumps(backend_evaluation_report(), ensure_ascii=False, indent=2))
        return 0
    model = (
        args.model
        or (
            get_local_stt_profile(args.profile).model
            if args.profile in LOCAL_STT_PROFILES
            else "base"
        )
    )
    recordings_dir = args.recordings_dir.expanduser().resolve()
    pairs = discover_pairs(recordings_dir)
    if args.pairs:
        requested = set(args.pairs)
        pairs = [pair for pair in pairs if pair.name in requested]
    if not pairs:
        raise SystemExit(f"No benchmark pairs found under {recordings_dir}")

    options = resolve_options(args)
    glossary = (
        [
            line.strip()
            for line in args.glossary_file.expanduser().resolve().read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if args.glossary_file
        else []
    )
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else REPOSITORY_ROOT
        / "build"
        / "stt-benchmarks"
        / f"{timestamp}-{args.profile}-{model}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    runtime = LocalRuntimeManager()
    model_root = default_model_dir() / "whisper"
    legacy_model_path = model_root / model
    results: list[dict[str, object]] = []
    failures = 0

    for pair in pairs:
        last_stage: str | None = None
        audio_preflight: dict[str, object] | None = None
        if args.audio_preflight or args.preflight_only:
            try:
                audio_preflight = runtime.run_feature(
                    "whisper",
                    {
                        "action": "audio_preflight",
                        "audio_path": str(pair.audio_path),
                    },
                    timeout=None,
                )
            except Exception as exc:
                audio_preflight = {"error": str(exc)}
        if args.preflight_only:
            results.append(
                {
                    "name": pair.name,
                    "audio_path": str(pair.audio_path),
                    "reference_path": str(pair.reference_path),
                    "audio_preflight": audio_preflight,
                }
            )
            continue

        def progress(
            stage: str,
            _completed: int | float | None,
            _total: int | float | None,
            message: str,
        ) -> None:
            nonlocal last_stage
            if stage != last_stage:
                print(f"[{pair.name}] {stage}: {message}", flush=True)
                last_stage = stage

        request = {
            "action": "whisper",
            "audio_path": str(pair.audio_path),
            "model": model,
            "model_path": (
                str(legacy_model_path) if legacy_model_path.is_dir() else None
            ),
            "download_root": str(model_root),
            "language": args.language,
            "quality_retry_enabled": args.quality_retry,
            "quality_retry_model": (
                get_local_stt_profile("quality-retry").model
                if args.quality_retry
                else None
            ),
            "quality_retry_beam_size": 5,
            "quality_retry_context_seconds": 1.5,
            "quality_retry_max_windows": 8,
            "quality_retry_max_seconds": 120.0,
            "auto_cpu_threads": True,
            **options,
            "hotwords": str(options.get("hotwords") or " ".join(glossary) or "") or None,
        }
        run_timings: list[float] = []
        response: dict[str, object] = {}
        try:
            for run_index in range(args.runs):
                started = time.perf_counter()
                response = runtime.run_feature(
                    "whisper",
                    request,
                    progress=progress,
                    timeout=None,
                )
                run_timings.append(time.perf_counter() - started)
        except Exception as exc:
            failures += 1
            result = {
                "name": pair.name,
                "audio_path": str(pair.audio_path),
                "reference_path": str(pair.reference_path),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "wall_seconds": (
                    run_timings[-1]
                    if run_timings
                    else time.perf_counter() - started
                ),
            }
            results.append(result)
            print(f"[{pair.name}] failed: {exc}", file=sys.stderr, flush=True)
            continue
        wall_seconds = run_timings[-1]
        reference = pair.reference_path.read_text(encoding="utf-8")
        metadata = dict(response.get("metadata") or {})
        duration = float(metadata.get("duration_seconds") or 0)
        primary_segments = [
            segment
            for segment in response.get("segments", [])
            if isinstance(segment, dict)
        ]
        retry_segments = [
            segment
            for segment in response.get("retry_segments", [])
            if isinstance(segment, dict)
        ]
        segments = merge_segment_payloads(
            primary_segments,
            retry_segments,
            [
                value
                for value in response.get("retry_windows", [])
                if isinstance(value, (list, tuple)) and len(value) == 2
            ],
        )
        hypothesis = " ".join(
            str(segment.get("text") or "").strip()
            for segment in segments
            if str(segment.get("text") or "").strip()
        )

        metrics = evaluate_text(reference, hypothesis, glossary=glossary)
        hypothesis_path = output_path.with_name(
            f"{output_path.stem}-{pair.name}-hypothesis.txt"
        )
        hypothesis_path.write_text(hypothesis, encoding="utf-8")

        result = {
            "name": pair.name,
            "audio_path": str(pair.audio_path),
            "reference_path": str(pair.reference_path),
            "hypothesis_path": str(hypothesis_path),
            "audio_duration_seconds": duration,
            "wall_seconds": wall_seconds,
            "run_wall_seconds": run_timings,
            "cold_start_wall_seconds": run_timings[0],
            "warm_start_wall_seconds": (
                mean(run_timings[1:]) if len(run_timings) > 1 else None
            ),
            "rtf": wall_seconds / duration if duration else 0,
            **metrics,
            "reference_alignment_warning": (
                "Reference and hypothesis lengths differ substantially; "
                "treat CER/WER as comparative, not absolute."
                if metrics["reference_character_count"]
                and not 0.67
                <= float(metrics["hypothesis_to_reference_character_ratio"])
                <= 1.5
                else None
            ),
            "confidence": confidence_summary(segments),
            "hallucination": {
                "high_no_speech_segment_count": confidence_summary(segments)[
                    "high_no_speech_segment_count"
                ],
                "repetition_region_count": metrics["repetition"][
                    "immediate_repeated_ngram_count"
                ],
            },
            "runtime": metadata,
            "audio_preflight": audio_preflight,
        }
        if args.refined_dir:
            refined_path = (
                args.refined_dir.expanduser().resolve() / f"refined-{pair.name}.md"
            )
            if refined_path.is_file():
                refined_text = refined_path.read_text(encoding="utf-8")
                result["refined"] = {
                    **evaluate_text(reference, refined_text, glossary=glossary),
                    "safety_audit": audit_refinement(
                        hypothesis,
                        refined_text,
                    ).to_dict(),
                }
        results.append(result)
        print(
            f"[{pair.name}] wall={wall_seconds:.2f}s rtf={result['rtf']:.4f} "
            f"cer={result['cer']:.4f} wer={result['wer']:.4f}",
            flush=True,
        )

    report: dict[str, object] = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "recordings_dir": str(recordings_dir),
        "profile": args.profile,
        "model": model,
        "language": args.language,
        "runs": args.runs,
        "glossary": glossary,
        "options": options,
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpu_count": __import__("os").cpu_count(),
            "physical_cpu_count": physical_cpu_count(),
        },
        "results": results,
    }
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(output_path.with_suffix(".md"), report)
    runtime.close()
    print(output_path)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
