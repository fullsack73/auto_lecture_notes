from __future__ import annotations

import argparse
import json
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
        "low_logprob_segment_count": sum(value < -1.0 for value in logprobs),
        "high_compression_segment_count": sum(
            value > 2.4 for value in compression_ratios
        ),
        "high_no_speech_segment_count": sum(
            value > 0.6 for value in no_speech_probs
        ),
    }


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
    parser.add_argument("--profile", choices=("baseline", "optimized"), default="baseline")
    parser.add_argument("--model", default="base")
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
        "| Pair | Audio min | Wall s | RTF | CER | WER | Segments |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in report["results"]:  # type: ignore[union-attr]
        if result.get("error"):
            lines.append(
                f"| {result['name']} | - | - | - | - | - | failed: "
                f"{str(result['error']).replace('|', '/')} |"
            )
            continue
        if "rtf" not in result:
            preflight = result.get("audio_preflight") or {}
            minutes = float(preflight.get("duration_seconds") or 0) / 60
            lines.append(
                f"| {result['name']} | {minutes:.2f} | - | - | - | - | "
                "preflight only |"
            )
            continue
        lines.append(
            "| {name} | {minutes:.2f} | {wall:.2f} | {rtf:.4f} | "
            "{cer:.4f} | {wer:.4f} | {segments} |".format(
                name=result["name"],
                minutes=float(result["audio_duration_seconds"]) / 60,
                wall=float(result["wall_seconds"]),
                rtf=float(result["rtf"]),
                cer=float(result["cer"]),
                wer=float(result["wer"]),
                segments=result["confidence"]["segment_count"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    recordings_dir = args.recordings_dir.expanduser().resolve()
    pairs = discover_pairs(recordings_dir)
    if args.pairs:
        requested = set(args.pairs)
        pairs = [pair for pair in pairs if pair.name in requested]
    if not pairs:
        raise SystemExit(f"No benchmark pairs found under {recordings_dir}")

    options = resolve_options(args)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else REPOSITORY_ROOT
        / "build"
        / "stt-benchmarks"
        / f"{timestamp}-{args.profile}-{args.model}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    runtime = LocalRuntimeManager()
    model_root = default_model_dir() / "whisper"
    legacy_model_path = model_root / args.model
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
            "model": args.model,
            "model_path": (
                str(legacy_model_path) if legacy_model_path.is_dir() else None
            ),
            "download_root": str(model_root),
            "language": args.language,
            **options,
        }
        started = time.perf_counter()
        try:
            response = runtime.run_feature(
                "whisper",
                request,
                progress=progress,
                timeout=None,
            )
        except Exception as exc:
            failures += 1
            result = {
                "name": pair.name,
                "audio_path": str(pair.audio_path),
                "reference_path": str(pair.reference_path),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "wall_seconds": time.perf_counter() - started,
            }
            results.append(result)
            print(f"[{pair.name}] failed: {exc}", file=sys.stderr, flush=True)
            continue
        wall_seconds = time.perf_counter() - started
        hypothesis = str(response.get("transcript_text") or "")
        reference = pair.reference_path.read_text(encoding="utf-8")
        metadata = dict(response.get("metadata") or {})
        duration = float(metadata.get("duration_seconds") or 0)
        segments = [
            segment
            for segment in response.get("segments", [])
            if isinstance(segment, dict)
        ]

        reference_characters = normalize_characters(reference)
        hypothesis_characters = normalize_characters(hypothesis)
        reference_words = normalize_words(reference)
        hypothesis_words = normalize_words(hypothesis)
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
            "rtf": wall_seconds / duration if duration else 0,
            "cer": error_rate(reference_characters, hypothesis_characters),
            "wer": error_rate(reference_words, hypothesis_words),
            "reference_character_count": len(reference_characters),
            "hypothesis_character_count": len(hypothesis_characters),
            "reference_word_count": len(reference_words),
            "hypothesis_word_count": len(hypothesis_words),
            "hypothesis_to_reference_character_ratio": (
                len(hypothesis_characters) / len(reference_characters)
                if reference_characters
                else None
            ),
            "reference_alignment_warning": (
                "Reference and hypothesis lengths differ substantially; "
                "treat CER/WER as comparative, not absolute."
                if reference_characters
                and not 0.67
                <= len(hypothesis_characters) / len(reference_characters)
                <= 1.5
                else None
            ),
            "repetition": repetition_summary(hypothesis_words),
            "confidence": confidence_summary(segments),
            "runtime": metadata,
            "audio_preflight": audio_preflight,
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
        "model": args.model,
        "language": args.language,
        "options": options,
        "results": results,
    }
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(output_path.with_suffix(".md"), report)
    print(output_path)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
