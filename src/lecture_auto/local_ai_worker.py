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
    emit("progress", stage="loading_model", completed=0, total=3, message="Loading Whisper model")
    from faster_whisper import WhisperModel

    model = str(request.get("model") or "base")
    model_path = request.get("model_path")
    model_source = str(model_path) if model_path and Path(str(model_path)).is_dir() else model
    kwargs: dict[str, Any] = {
        "device": "cpu",
        "compute_type": str(request.get("compute_type") or "int8"),
    }
    download_root = request.get("download_root")
    if download_root and model_source == model:
        kwargs["download_root"] = str(download_root)
    runtime = WhisperModel(model_source, **kwargs)
    emit("progress", stage="transcribing", completed=1, total=3, message="Transcribing audio")
    transcribe_kwargs: dict[str, Any] = {}
    if request.get("language"):
        transcribe_kwargs["language"] = request["language"]
    raw_segments, info = runtime.transcribe(str(request["audio_path"]), **transcribe_kwargs)
    segments: list[dict[str, Any]] = []
    text_parts: list[str] = []
    duration = float(getattr(info, "duration", 0) or 0)
    for segment in raw_segments:
        text = str(segment.text).strip()
        text_parts.append(text)
        segments.append({
            "speaker": "Speaker 1",
            "start_time": float(segment.start),
            "end_time": float(segment.end),
            "text": text,
        })
        emit(
            "progress",
            stage="transcribing",
            completed=float(segment.end),
            total=duration or None,
            message=f"Transcribed {float(segment.end):.1f}s",
        )
    emit("progress", stage="complete", completed=3, total=3, message="Transcription complete")
    return {
        "transcript_text": " ".join(text_parts).strip(),
        "language": getattr(info, "language", None) or request.get("language"),
        "segments": segments,
    }


def download_whisper_model(request: dict[str, Any]) -> dict[str, Any]:
    emit("progress", stage="model_download", completed=0, total=None, message="Downloading Whisper model")
    from faster_whisper import WhisperModel

    model = str(request.get("model") or "base")
    download_root = Path(str(request["download_root"]))
    download_root.mkdir(parents=True, exist_ok=True)
    WhisperModel(model, device="cpu", compute_type="int8", download_root=str(download_root))
    emit("progress", stage="complete", completed=1, total=1, message="Whisper model ready")
    return {"model": model, "download_root": str(download_root)}


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
