"""Standalone JSON Lines worker executed by an external local-AI Python runtime."""
from __future__ import annotations

import os
import sys

_WORKER_DIR = os.path.normcase(os.path.abspath(os.path.dirname(__file__)))
if sys.path and os.path.normcase(os.path.abspath(sys.path[0])) == _WORKER_DIR:
    sys.path.pop(0)

import importlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any


PACKAGE_MODULES = {
    "faster_whisper": "faster_whisper",
    "ctranslate2": "ctranslate2",
    "torch": "torch",
    "torchaudio": "torchaudio",
    "deepfilternet": "df",
    "onnxruntime": "onnxruntime",
    "google_genai": "google.genai",
}

TORCHAUDIO_COMPAT = r'''
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
        return AudioMetaData(wav.getframerate(), wav.getnframes(), wav.getnchannels(), wav.getsampwidth() * 8)

def _wave_load(file, frame_offset=0, num_frames=-1, channels_first=True, **kwargs):
    if torch is None:
        raise ImportError("torch is required to load WAV audio")
    with wave.open(str(file), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        if wav.getsampwidth() != 2:
            raise RuntimeError("Only 16-bit PCM WAV files are supported")
        if frame_offset:
            wav.setpos(frame_offset)
        count = wav.getnframes() - frame_offset if num_frames < 0 else num_frames
        raw = wav.readframes(count)
    audio = torch.frombuffer(bytearray(raw), dtype=torch.int16).to(torch.float32)
    audio = audio.reshape(-1, channels) / 32768.0
    return (audio.t().contiguous() if channels_first else audio), sample_rate

def _wave_save(file, src, sample_rate, channels_first=True, **kwargs):
    if torch is None:
        raise ImportError("torch is required to save WAV audio")
    audio = torch.as_tensor(src).detach().cpu()
    if channels_first:
        audio = audio.t()
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    pcm = ((audio.clamp(-1.0, 1.0) * 32767.0).to(torch.int16) if audio.dtype.is_floating_point else audio.to(torch.int16))
    with wave.open(str(file), "wb") as wav:
        wav.setnchannels(audio.shape[1])
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.contiguous().numpy().tobytes())

if torchaudio is not None:
    torchaudio.info = _wave_info
    torchaudio.load = _wave_load
    torchaudio.save = _wave_save
backend = types.ModuleType("torchaudio.backend")
common = types.ModuleType("torchaudio.backend.common")
common.AudioMetaData = AudioMetaData
backend.common = common
sys.modules["torchaudio.backend"] = backend
sys.modules["torchaudio.backend.common"] = common
'''


def emit(event_type: str, **payload: Any) -> None:
    print(json.dumps({"type": event_type, **payload}, ensure_ascii=False), flush=True)


def package_probe(distribution: str, module_name: str) -> dict[str, Any]:
    try:
        found = importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError):
        found = False
    result: dict[str, Any] = {
        "found": found,
        "import_ok": False,
        "version": None,
        "error": None,
    }
    if not result["found"]:
        return result
    try:
        module = importlib.import_module(module_name)
        try:
            package_name = "google-genai" if distribution == "google_genai" else distribution
            result["version"] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            result["version"] = getattr(module, "__version__", None)
        result["import_ok"] = True
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def probe() -> dict[str, Any]:
    packages = {}
    for name, module_name in PACKAGE_MODULES.items():
        if name == "deepfilternet":
            exec(TORCHAUDIO_COMPAT, {})
        packages[name] = package_probe(name, module_name)
    return {
        "python_path": str(Path(sys.executable).resolve()),
        "python_version": platform.python_version(),
        "architecture": platform.machine(),
        "packages": packages,
    }


def whisper(request: dict[str, Any]) -> dict[str, Any]:
    started_at = time.perf_counter()
    emit("progress", stage="loading_model", completed=0, total=3, message="Loading Whisper model")
    from faster_whisper import WhisperModel

    model = str(request.get("model") or "base")
    model_path = request.get("model_path")
    model_source = str(model_path) if model_path and Path(str(model_path)).is_dir() else model
    requested_device = str(request.get("device") or "cpu")
    device = requested_device
    ctranslate2 = None
    if requested_device == "auto":
        import ctranslate2 as ctranslate2_module

        ctranslate2 = ctranslate2_module
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    requested_compute_type = str(request.get("compute_type") or "int8")
    compute_type = requested_compute_type
    if ctranslate2 is None:
        import ctranslate2 as ctranslate2_module

        ctranslate2 = ctranslate2_module
    supported = ctranslate2.get_supported_compute_types(device)
    if requested_compute_type == "auto":
        if device == "cuda":
            compute_type = "float16" if "float16" in supported else "int8_float16"
        else:
            compute_type = "int8" if "int8" in supported else "float32"
    kwargs: dict[str, Any] = {
        "device": device,
        "compute_type": compute_type,
    }
    cpu_threads = int(request.get("cpu_threads") or 0)
    if cpu_threads > 0:
        kwargs["cpu_threads"] = cpu_threads
    num_workers = int(request.get("num_workers") or 1)
    if num_workers > 1:
        kwargs["num_workers"] = num_workers
    download_root = request.get("download_root")
    if download_root and model_source == model:
        kwargs["download_root"] = str(download_root)
    try:
        runtime = WhisperModel(model_source, **kwargs)
    except Exception as exc:
        if device == "cuda":
            raise RuntimeError(
                "CUDA Whisper initialization failed. Install compatible CUDA 12 "
                "cuBLAS/cuDNN libraries or explicitly select device=cpu. "
                f"Original error: {exc}"
            ) from exc
        raise
    model_loaded_at = time.perf_counter()
    emit("progress", stage="transcribing", completed=1, total=3, message="Transcribing audio")
    transcribe_kwargs: dict[str, Any] = {}
    if request.get("language"):
        transcribe_kwargs["language"] = request["language"]
    transcribe_kwargs["beam_size"] = int(request.get("beam_size") or 5)
    if request.get("temperature") is not None:
        transcribe_kwargs["temperature"] = float(request["temperature"])
    transcribe_kwargs["vad_filter"] = bool(request.get("vad_filter", False))
    if transcribe_kwargs["vad_filter"]:
        transcribe_kwargs["vad_parameters"] = {
            "min_silence_duration_ms": int(
                request.get("vad_min_silence_duration_ms") or 2000
            )
        }
    transcribe_kwargs["condition_on_previous_text"] = bool(
        request.get("condition_on_previous_text", True)
    )
    transcribe_kwargs["word_timestamps"] = bool(request.get("word_timestamps", False))
    if request.get("hotwords"):
        transcribe_kwargs["hotwords"] = str(request["hotwords"])

    requested_batch_size = int(request.get("batch_size") or 1)
    if requested_batch_size > 1 and not transcribe_kwargs["vad_filter"]:
        raise ValueError("Batched Whisper transcription requires vad_filter=true")

    effective_batch_size = requested_batch_size
    batch_retry_count = 0
    while True:
        attempt_kwargs = dict(transcribe_kwargs)
        transcriber: Any = runtime
        if effective_batch_size > 1:
            from faster_whisper import BatchedInferencePipeline

            transcriber = BatchedInferencePipeline(model=runtime)
            attempt_kwargs["batch_size"] = effective_batch_size

        segments = []
        text_parts = []
        try:
            raw_segments, info = transcriber.transcribe(
                str(request["audio_path"]),
                **attempt_kwargs,
            )
            duration = float(getattr(info, "duration", 0) or 0)
            for segment in raw_segments:
                text = str(segment.text).strip()
                text_parts.append(text)
                segments.append({
                    "speaker": "Speaker 1",
                    "start_time": float(segment.start),
                    "end_time": float(segment.end),
                    "text": text,
                    "avg_logprob": _optional_float(getattr(segment, "avg_logprob", None)),
                    "compression_ratio": _optional_float(
                        getattr(segment, "compression_ratio", None)
                    ),
                    "no_speech_prob": _optional_float(
                        getattr(segment, "no_speech_prob", None)
                    ),
                    "temperature": _optional_float(
                        getattr(segment, "temperature", None)
                    ),
                    "words": [
                        {
                            "word": str(getattr(word, "word", "")),
                            "start_time": float(getattr(word, "start", 0) or 0),
                            "end_time": float(getattr(word, "end", 0) or 0),
                            "probability": _optional_float(
                                getattr(word, "probability", None)
                            ),
                        }
                        for word in (getattr(segment, "words", None) or [])
                    ],
                })
                emit(
                    "progress",
                    stage="transcribing",
                    completed=float(segment.end),
                    total=duration or None,
                    message=f"Transcribed {float(segment.end):.1f}s",
                )
            break
        except RuntimeError as exc:
            if effective_batch_size <= 1 or not _is_memory_exhaustion(exc):
                raise
            effective_batch_size = max(1, effective_batch_size // 2)
            batch_retry_count += 1
            emit(
                "progress",
                stage="batch_retry",
                completed=None,
                total=None,
                message=(
                    "Whisper memory limit reached; retrying with batch size "
                    f"{effective_batch_size}"
                ),
            )
    emit("progress", stage="complete", completed=3, total=3, message="Transcription complete")
    finished_at = time.perf_counter()
    return {
        "transcript_text": " ".join(text_parts).strip(),
        "language": getattr(info, "language", None) or request.get("language"),
        "segments": segments,
        "metadata": {
            "model": model,
            "requested_device": requested_device,
            "device": device,
            "requested_compute_type": requested_compute_type,
            "compute_type": compute_type,
            "requested_batch_size": requested_batch_size,
            "batch_size": effective_batch_size,
            "batch_retry_count": batch_retry_count,
            "beam_size": transcribe_kwargs["beam_size"],
            "vad_filter": transcribe_kwargs["vad_filter"],
            "duration_seconds": duration,
            "duration_after_vad_seconds": float(
                getattr(info, "duration_after_vad", duration) or 0
            ),
            "language_probability": _optional_float(
                getattr(info, "language_probability", None)
            ),
            "model_load_seconds": model_loaded_at - started_at,
            "transcription_seconds": finished_at - model_loaded_at,
            "worker_total_seconds": finished_at - started_at,
            "python_version": platform.python_version(),
            "faster_whisper_version": _package_version("faster-whisper"),
            "ctranslate2_version": _package_version("ctranslate2"),
            "supported_compute_types": sorted(supported),
            "cuda_device_count": ctranslate2.get_cuda_device_count(),
            "cpu_count": os.cpu_count(),
            "platform": platform.platform(),
        },
    }


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _is_memory_exhaustion(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "out of memory",
            "cuda_error_out_of_memory",
            "cudnn_status_alloc_failed",
            "std::bad_alloc",
            "failed to allocate",
        )
    )


def download_whisper_model(request: dict[str, Any]) -> dict[str, Any]:
    emit("progress", stage="model_download", completed=0, total=None, message="Downloading Whisper model")
    from faster_whisper import WhisperModel

    model = str(request.get("model") or "base")
    download_root = Path(str(request["download_root"]))
    download_root.mkdir(parents=True, exist_ok=True)
    WhisperModel(model, device="cpu", compute_type="int8", download_root=str(download_root))
    emit("progress", stage="complete", completed=1, total=1, message="Whisper model ready")
    return {"model": model, "download_root": str(download_root)}


def audio_preflight(request: dict[str, Any]) -> dict[str, Any]:
    import math

    import av
    import numpy as np

    source = Path(str(request["audio_path"])).resolve()
    emit(
        "progress",
        stage="audio_preflight",
        completed=0,
        total=None,
        message="Analyzing audio levels and silence",
    )
    with av.open(str(source)) as container:
        stream = next(
            (candidate for candidate in container.streams if candidate.type == "audio"),
            None,
        )
        if stream is None:
            raise ValueError("Input contains no audio stream")
        duration = (
            float(container.duration / av.time_base)
            if container.duration is not None
            else float(stream.duration * stream.time_base)
            if stream.duration is not None and stream.time_base is not None
            else 0.0
        )
        original_rate = int(getattr(stream.codec_context, "sample_rate", 0) or 0)
        original_channels = int(getattr(stream.codec_context, "channels", 0) or 0)
        codec_name = str(getattr(stream.codec_context, "name", "") or "") or None
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
        window_size = 8000
        silence_threshold = 10 ** (-40 / 20)
        carry = np.empty(0, dtype=np.float32)
        sample_count = 0
        square_sum = 0.0
        peak = 0.0
        clipping_sample_count = 0
        silent_sample_count = 0

        def consume(resampled_frame: Any) -> None:
            nonlocal carry
            nonlocal sample_count
            nonlocal square_sum
            nonlocal peak
            nonlocal clipping_sample_count
            nonlocal silent_sample_count
            samples = np.asarray(
                resampled_frame.to_ndarray(),
                dtype=np.float32,
            ).reshape(-1)
            if samples.size == 0:
                return
            absolute = np.abs(samples)
            sample_count += int(samples.size)
            samples64 = samples.astype(np.float64)
            square_sum += float(np.dot(samples64, samples64))
            peak = max(peak, float(absolute.max()))
            clipping_sample_count += int(np.count_nonzero(absolute >= 0.999))
            carry = np.concatenate((carry, samples))
            while carry.size >= window_size:
                window = carry[:window_size]
                carry = carry[window_size:]
                window64 = window.astype(np.float64)
                rms = math.sqrt(float(np.dot(window64, window64)) / window_size)
                if rms <= silence_threshold:
                    silent_sample_count += window_size

        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                consume(resampled)
            frame_end = float(frame.time or 0)
            emit(
                "progress",
                stage="audio_preflight",
                completed=frame_end,
                total=duration or None,
                message=f"Analyzed {frame_end:.1f}s",
            )
        for resampled in resampler.resample(None):
            consume(resampled)

    rms = math.sqrt(square_sum / sample_count) if sample_count else 0.0
    mean_volume_db = 20 * math.log10(rms) if rms > 0 else None
    max_volume_db = 20 * math.log10(peak) if peak > 0 else None
    analyzed_duration = sample_count / 16000
    silence_seconds = silent_sample_count / 16000
    silence_ratio = (
        min(1.0, silence_seconds / analyzed_duration)
        if analyzed_duration
        else 0.0
    )
    clipping_ratio = clipping_sample_count / sample_count if sample_count else 0.0
    clipping_risk = clipping_ratio >= 0.0001 or peak >= 1.0
    low_loudness = mean_volume_db is not None and mean_volume_db < -30.0
    recommendations: list[str] = []
    if silence_ratio >= 0.10:
        recommendations.append("enable_vad")
    if low_loudness and not clipping_risk:
        recommendations.append("benchmark_loudness_normalization")
    if clipping_risk:
        recommendations.append("avoid_positive_gain_and_check_capture_level")
    if original_rate != 16000 or original_channels != 1:
        recommendations.append(
            "let_whisper_resample_or_cache_16khz_mono_only_for_reuse"
        )
    emit(
        "progress",
        stage="complete",
        completed=1,
        total=1,
        message="Audio preflight complete",
    )
    return {
        "duration_seconds": duration or analyzed_duration,
        "sample_rate": original_rate or None,
        "channels": original_channels or None,
        "codec_name": codec_name,
        "mean_volume_db": mean_volume_db,
        "max_volume_db": max_volume_db,
        "clipping_ratio": clipping_ratio,
        "silence_seconds": silence_seconds,
        "silence_ratio": silence_ratio,
        "clipping_risk": clipping_risk,
        "low_loudness": low_loudness,
        "recommendations": recommendations,
    }


def _deepfilter_executable() -> Path:
    scripts = Path(sys.executable).parent
    name = "deepFilter.exe" if os.name == "nt" else "deepFilter"
    executable = scripts / name
    if not executable.is_file():
        resolved = shutil.which("deepFilter")
        if resolved:
            return Path(resolved)
    return executable


def deepfilter(request: dict[str, Any]) -> dict[str, Any]:
    source = Path(str(request["audio_path"]))
    destination = Path(str(request["output_path"]))
    if not source.is_file():
        raise FileNotFoundError(f"Audio file not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    emit("progress", stage="noise_reduction", completed=0, total=2, message="Running DeepFilterNet")
    with tempfile.TemporaryDirectory(prefix="lecture_auto_df_worker_") as temporary:
        output_dir = Path(temporary)
        sitecustomize = output_dir / "sitecustomize.py"
        sitecustomize.write_text(TORCHAUDIO_COMPAT, encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            value for value in (str(output_dir), env.get("PYTHONPATH")) if value
        )
        command = [str(_deepfilter_executable()), str(source), "-o", str(output_dir), "--log-level", "none"]
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, env=env)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-1000:]
            raise RuntimeError(f"DeepFilterNet failed ({completed.returncode}): {detail}")
        candidates = [path for path in output_dir.iterdir() if path.is_file()]
        if not candidates:
            raise RuntimeError("DeepFilterNet produced no output file.")
        chosen = next((path for path in candidates if path.stem.startswith(source.stem)), candidates[0])
        shutil.copy2(chosen, destination)
    emit("progress", stage="complete", completed=2, total=2, message="Noise reduction complete")
    return {"output_path": str(destination)}


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    action = request.get("action")
    if action == "probe":
        return probe()
    if action == "whisper":
        return whisper(request)
    if action == "download_whisper_model":
        return download_whisper_model(request)
    if action == "audio_preflight":
        return audio_preflight(request)
    if action == "deepfilter":
        return deepfilter(request)
    raise ValueError(f"Unknown worker action: {action}")


def main() -> None:
    line = sys.stdin.readline()
    if not line:
        emit("error", code="EMPTY_REQUEST", message="Worker request was not provided.")
        raise SystemExit(2)
    try:
        request = json.loads(line)
        emit("progress", stage="started", completed=0, total=None, message="Worker started")
        result = dispatch(request)
        emit("result", result=result)
    except BaseException as exc:
        emit(
            "error",
            code=type(exc).__name__,
            message=str(exc),
            traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:],
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
