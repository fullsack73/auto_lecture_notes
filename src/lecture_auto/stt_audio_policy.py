from __future__ import annotations

import hashlib
import subprocess
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Mapping

from lecture_auto.capture_runtime import resolve_ffmpeg_bin


@dataclass(frozen=True)
class AudioCandidateDecision:
    selected: str
    reason: str
    candidates: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["candidates"] = list(self.candidates)
        return value


def conditional_audio_filters(
    preflight: Mapping[str, object],
    *,
    persistent_noise: bool = False,
    low_frequency_rumble: bool = False,
) -> tuple[str, ...]:
    """Select only evidence-backed filters; raw audio always remains a candidate."""
    filters: list[str] = []
    low_loudness = bool(preflight.get("low_loudness"))
    clipping_risk = bool(preflight.get("clipping_risk"))
    if low_loudness and not clipping_risk:
        filters.append("loudnorm=I=-20:LRA=11:TP=-1.5")
    if low_frequency_rumble:
        filters.append("highpass=f=80")
    if persistent_noise:
        filters.append("deepfilternet")
    return tuple(filters)


def capture_source_recommendation(
    *,
    capture_source: str,
    playback_audio_expected: bool,
) -> str | None:
    if playback_audio_expected and capture_source == "microphone":
        return (
            "Prefer system loopback/monitor capture for played lecture audio; "
            "use the microphone only when room speech is required."
        )
    return None


def choose_audio_candidate(
    metrics: Mapping[str, Mapping[str, float | int | None]],
) -> AudioCandidateDecision:
    """Choose the lowest CER, then highest term recall, while retaining raw on ties."""
    if "raw" not in metrics:
        raise ValueError("Audio candidate metrics must include 'raw'.")

    def score(item: tuple[str, Mapping[str, float | int | None]]) -> tuple[float, float, int]:
        name, values = item
        cer = float(values.get("cer") if values.get("cer") is not None else float("inf"))
        recall = float(
            values.get("term_recall") if values.get("term_recall") is not None else 0.0
        )
        return (cer, -recall, 0 if name == "raw" else 1)

    selected, selected_metrics = min(metrics.items(), key=score)
    raw_metrics = metrics["raw"]
    raw_cer = float(
        raw_metrics.get("cer")
        if raw_metrics.get("cer") is not None
        else float("inf")
    )
    selected_cer = float(
        selected_metrics.get("cer")
        if selected_metrics.get("cer") is not None
        else float("inf")
    )
    if selected != "raw" and selected_cer >= raw_cer:
        selected = "raw"
        reason = "Processed input did not improve CER; preserved the original path."
    else:
        reason = "Selected the best measured CER/term-recall candidate."
    return AudioCandidateDecision(
        selected=selected,
        reason=reason,
        candidates=tuple(metrics),
    )


@contextmanager
def canonical_audio_input(
    *,
    audio_path: str | Path,
    cache_dir: str | Path,
    expected_uses: int,
    ffmpeg_bin: str | None = None,
) -> Iterator[Path]:
    """Cache 16 kHz mono FLAC only when an input will be decoded repeatedly."""
    source = Path(audio_path).expanduser().resolve()
    if expected_uses < 2:
        yield source
        return
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cache_root = Path(cache_dir).expanduser().resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / f"{digest}.16k-mono.flac"
    if not target.is_file():
        command = [
            ffmpeg_bin or resolve_ffmpeg_bin(),
            "-y",
            "-i",
            str(source),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "flac",
            str(target),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            target.unlink(missing_ok=True)
            raise RuntimeError(
                "Failed to create canonical STT audio: "
                + (completed.stderr or completed.stdout)[-500:]
            )
    yield target
