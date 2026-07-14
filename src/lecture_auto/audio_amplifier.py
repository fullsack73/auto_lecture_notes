from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from lecture_auto.capture_runtime import resolve_ffmpeg_bin


class AudioAmplificationError(RuntimeError):
    """Raised when preparing amplified audio input fails."""


class AudioFilterError(RuntimeError):
    """Raised when audio filtering/noise reduction fails."""


_DEEPFILTER_SITE_CUSTOMIZE = r"""
import sys
import types
import wave

try:
    import torch
    import torchaudio
except ImportError:
    torch = None
    torchaudio = None


class AudioMetaData:
    def __init__(self, sample_rate, num_frames, num_channels, bits_per_sample=16):
        self.sample_rate = sample_rate
        self.num_frames = num_frames
        self.num_channels = num_channels
        self.bits_per_sample = bits_per_sample
        self.encoding = "PCM_S"


def _wave_info(file, **kwargs):
    with wave.open(str(file), "rb") as wav:
        return AudioMetaData(
            sample_rate=wav.getframerate(),
            num_frames=wav.getnframes(),
            num_channels=wav.getnchannels(),
            bits_per_sample=wav.getsampwidth() * 8,
        )


def _wave_load(file, frame_offset=0, num_frames=-1, channels_first=True, **kwargs):
    if torch is None:
        raise ImportError("torch is required to load WAV audio")
    with wave.open(str(file), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        if sample_width != 2:
            raise RuntimeError("Only 16-bit PCM WAV files are supported by this fallback")
        if frame_offset:
            wav.setpos(frame_offset)
        frames_to_read = wav.getnframes() - frame_offset if num_frames < 0 else num_frames
        raw = wav.readframes(frames_to_read)
    audio = torch.frombuffer(bytearray(raw), dtype=torch.int16).to(torch.float32)
    audio = audio.reshape(-1, channels) / 32768.0
    if channels_first:
        audio = audio.t().contiguous()
    return audio, sample_rate


def _wave_save(file, src, sample_rate, channels_first=True, **kwargs):
    if torch is None:
        raise ImportError("torch is required to save WAV audio")
    audio = torch.as_tensor(src).detach().cpu()
    if channels_first:
        audio = audio.t()
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    if audio.dtype.is_floating_point:
        pcm_audio = (audio.clamp(-1.0, 1.0) * 32767.0).to(torch.int16)
    else:
        pcm_audio = audio.to(torch.int16)
    pcm = pcm_audio.contiguous().numpy().tobytes()
    with wave.open(str(file), "wb") as wav:
        wav.setnchannels(audio.shape[1])
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm)


if torchaudio is not None:
    torchaudio.info = _wave_info
    torchaudio.load = _wave_load
    torchaudio.save = _wave_save

backend_module = types.ModuleType("torchaudio.backend")
backend_common_module = types.ModuleType("torchaudio.backend.common")
backend_common_module.AudioMetaData = AudioMetaData
backend_module.common = backend_common_module
sys.modules["torchaudio.backend"] = backend_module
sys.modules["torchaudio.backend.common"] = backend_common_module
"""


def _select_deepfilter_output(output_dir: Path, source: Path) -> Path:
    candidates = [
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".wav", ".flac", ".mp3", ".ogg"}
    ]
    exact = output_dir / source.name
    if exact in candidates:
        return exact

    stem_matches = [path for path in candidates if path.stem.startswith(source.stem)]
    if len(stem_matches) == 1:
        return stem_matches[0]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        names = ", ".join(sorted(path.name for path in candidates))
        raise AudioFilterError(
            "deepFilter produced multiple possible output files; could not choose one. "
            f"Candidates: {names}"
        )
    raise AudioFilterError(
        "deepFilter finished but did not produce a filtered output file."
    )


@contextmanager
def deepfilter_audio_input(
    *,
    audio_path: str,
    deepfilter_bin: str = "deepFilter",
    ffmpeg_bin: str | None = None,
) -> Iterator[str]:
    """Yield a noise-reduced audio path using deepfilternet."""
    original_source = Path(audio_path)
    if not original_source.exists():
        raise AudioFilterError(f"Audio file does not exist: {audio_path}")

    with tempfile.TemporaryDirectory(prefix="lecture_auto_df_") as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        source_dir = tmp_dir_path / "input"
        output_dir = tmp_dir_path / "output"
        source_dir.mkdir()
        output_dir.mkdir()

        source = source_dir / f"{original_source.stem}_src.wav"
        ffmpeg_bin = ffmpeg_bin or resolve_ffmpeg_bin()
        ffmpeg_cmd = [
            ffmpeg_bin, "-y", "-v", "warning",
            "-i", str(original_source),
            "-c:a", "pcm_s16le",
            str(source),
        ]
        completed = subprocess.run(
            ffmpeg_cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0:
            raise AudioFilterError(
                f"Failed to convert {original_source.suffix} to WAV for filtering. "
                f"Detail: {completed.stderr}"
            )

        sitecustomize_path = tmp_dir_path / "sitecustomize.py"
        sitecustomize_path.write_text(_DEEPFILTER_SITE_CUSTOMIZE)

        env = dict(os.environ)
        env["PYTHONPATH"] = f"{tmp_dir_path}:{env.get('PYTHONPATH', '')}".strip(":")

        command = [
            deepfilter_bin,
            str(source),
            "-o",
            str(output_dir),
            "--log-level",
            "none",
        ]

        try:
            completed = subprocess.run(
                command,
                check=False,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise AudioFilterError(
                "deepFilter is required for noise reduction but was not found on PATH."
            ) from exc
        except OSError as exc:
            raise AudioFilterError(
                "Failed to start deepFilter for noise reduction."
            ) from exc

        if completed.returncode != 0:
            detail = (completed.stderr or "").strip()
            if len(detail) > 500:
                detail = detail[-500:]
            raise AudioFilterError(
                "deepFilter failed while reducing noise."
                + (f" Detail: {detail}" if detail else "")
            )

        output_path = _select_deepfilter_output(output_dir, source)

        yield str(output_path)


@contextmanager
def amplified_audio_input(
    *,
    audio_path: str,
    use_dynaudnorm: bool = False,
    dynaudnorm_f: int | None = None,
    dynaudnorm_g: int | None = None,
    gain_db: float | None = None,
    ffmpeg_bin: str | None = None,
) -> Iterator[str]:
    """Yield an audio path suitable for STT, amplifying input when needed.

    When use_dynaudnorm is False, this yields the original path with no side effects.
    """
    if not use_dynaudnorm:
        yield audio_path
        return

    source = Path(audio_path)
    if not source.exists():
        raise AudioAmplificationError(f"Audio file does not exist: {audio_path}")

    filter_opts = []
    if dynaudnorm_f is not None:
        filter_opts.append(f"f={dynaudnorm_f}")
    if dynaudnorm_g is not None:
        filter_opts.append(f"g={dynaudnorm_g}")
    
    dynaudnorm_str = "dynaudnorm"
    if filter_opts:
        dynaudnorm_str += "=" + ":".join(filter_opts)

    if gain_db is not None:
        dynaudnorm_str += f",volume={gain_db}dB"


    with tempfile.TemporaryDirectory(prefix="lecture_auto_amp_") as tmp_dir:
        ffmpeg_bin = ffmpeg_bin or resolve_ffmpeg_bin()
        output_path = Path(tmp_dir) / "amplified.wav"
        command = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(source),
            "-filter:a",
            dynaudnorm_str,
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]

        try:
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise AudioAmplificationError(
                "FFmpeg is required for audio amplification but was not found on PATH."
            ) from exc
        except OSError as exc:
            raise AudioAmplificationError(
                "Failed to start FFmpeg for audio amplification."
            ) from exc

        if completed.returncode != 0:
            detail = (completed.stderr or "").strip()
            if len(detail) > 500:
                detail = detail[-500:]
            raise AudioAmplificationError(
                "FFmpeg failed while amplifying audio input."
                + (f" Detail: {detail}" if detail else "")
            )

        if not output_path.exists():
            raise AudioAmplificationError(
                "FFmpeg finished but did not produce an amplified output file."
            )

        yield str(output_path)
