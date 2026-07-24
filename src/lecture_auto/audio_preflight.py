from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from lecture_auto.capture_runtime import resolve_ffmpeg_bin, resolve_ffprobe_bin


class AudioPreflightError(RuntimeError):
    """Raised when audio diagnostics cannot decode or inspect an input."""


@dataclass(frozen=True)
class AudioPreflightResult:
    duration_seconds: float
    sample_rate: int | None
    channels: int | None
    codec_name: str | None
    mean_volume_db: float | None
    max_volume_db: float | None
    silence_seconds: float
    silence_ratio: float
    clipping_risk: bool
    low_loudness: bool
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["recommendations"] = list(self.recommendations)
        return value


def analyze_audio_for_stt(audio_path: str | Path) -> AudioPreflightResult:
    path = Path(audio_path).expanduser().resolve()
    if not path.is_file():
        raise AudioPreflightError(f"Audio file does not exist: {path}")

    probe = _run(
        [
            resolve_ffprobe_bin(),
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        probe_payload = json.loads(probe.stdout)
        duration = float(probe_payload.get("format", {}).get("duration") or 0)
        audio_stream = next(
            (
                stream
                for stream in probe_payload.get("streams", [])
                if stream.get("codec_type") == "audio"
            ),
            {},
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AudioPreflightError("FFprobe returned invalid audio metadata.") from exc
    if duration <= 0:
        raise AudioPreflightError("Audio duration is unavailable or zero.")

    filters = _run(
        [
            resolve_ffmpeg_bin(),
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "volumedetect,silencedetect=noise=-40dB:d=0.5",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    if filters.returncode != 0:
        raise AudioPreflightError(
            f"FFmpeg audio diagnostics failed: {filters.stderr.strip()[-500:]}"
        )

    mean_volume = _last_float(filters.stderr, r"mean_volume:\s*(-?[\d.]+)\s*dB")
    max_volume = _last_float(filters.stderr, r"max_volume:\s*(-?[\d.]+)\s*dB")
    silence_seconds = sum(
        float(value)
        for value in re.findall(
            r"silence_duration:\s*([\d.]+)",
            filters.stderr,
        )
    )
    silence_seconds = min(duration, silence_seconds)
    silence_ratio = silence_seconds / duration
    clipping_risk = max_volume is not None and max_volume >= -0.1
    low_loudness = mean_volume is not None and mean_volume < -30.0

    recommendations: list[str] = []
    if silence_ratio >= 0.10:
        recommendations.append("enable_vad")
    if low_loudness and not clipping_risk:
        recommendations.append("benchmark_loudness_normalization")
    if clipping_risk:
        recommendations.append("avoid_positive_gain_and_check_capture_level")
    if (
        _optional_int(audio_stream.get("sample_rate")) != 16000
        or _optional_int(audio_stream.get("channels")) != 1
    ):
        recommendations.append(
            "let_whisper_resample_or_cache_16khz_mono_only_for_reuse"
        )

    return AudioPreflightResult(
        duration_seconds=duration,
        sample_rate=_optional_int(audio_stream.get("sample_rate")),
        channels=_optional_int(audio_stream.get("channels")),
        codec_name=(
            str(audio_stream["codec_name"])
            if audio_stream.get("codec_name") is not None
            else None
        ),
        mean_volume_db=mean_volume,
        max_volume_db=max_volume,
        silence_seconds=silence_seconds,
        silence_ratio=silence_ratio,
        clipping_risk=clipping_risk,
        low_loudness=low_loudness,
        recommendations=tuple(recommendations),
    )


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=check,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AudioPreflightError(f"Audio diagnostics command failed: {exc}") from exc


def _last_float(text: str, pattern: str) -> float | None:
    matches = re.findall(pattern, text)
    return float(matches[-1]) if matches else None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
