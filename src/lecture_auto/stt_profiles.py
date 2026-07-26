from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import asdict, dataclass
from typing import Literal


ProfileName = Literal[
    "cpu-fast",
    "cpu-balanced",
    "nvidia-balanced",
    "quality-retry",
]


@dataclass(frozen=True)
class LocalSTTProfile:
    name: ProfileName
    model: str
    device: str
    compute_type: str
    batch_size: int
    beam_size: int
    vad_filter: bool
    vad_min_silence_duration_ms: int = 1000
    condition_on_previous_text: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


LOCAL_STT_PROFILES: dict[ProfileName, LocalSTTProfile] = {
    "cpu-fast": LocalSTTProfile(
        name="cpu-fast",
        model="base",
        device="cpu",
        compute_type="int8",
        batch_size=4,
        beam_size=1,
        vad_filter=True,
    ),
    "cpu-balanced": LocalSTTProfile(
        name="cpu-balanced",
        model="small",
        device="cpu",
        compute_type="int8",
        batch_size=4,
        beam_size=1,
        vad_filter=True,
    ),
    "nvidia-balanced": LocalSTTProfile(
        name="nvidia-balanced",
        model="turbo",
        device="cuda",
        compute_type="float16",
        batch_size=4,
        beam_size=1,
        vad_filter=True,
    ),
    "quality-retry": LocalSTTProfile(
        name="quality-retry",
        model="large-v3",
        device="auto",
        compute_type="auto",
        batch_size=1,
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=True,
        vad_min_silence_duration_ms=2000,
    ),
}


def get_local_stt_profile(name: str) -> LocalSTTProfile:
    try:
        return LOCAL_STT_PROFILES[name]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(
            f"Unknown local STT profile '{name}'. "
            f"Use one of {', '.join(LOCAL_STT_PROFILES)}."
        ) from exc


def physical_cpu_count() -> int:
    """Return a conservative physical-core estimate without importing heavy packages."""
    system = platform.system()
    if system == "Linux":
        try:
            pairs: set[tuple[str, str]] = set()
            physical_id = ""
            core_id = ""
            for line in open("/proc/cpuinfo", encoding="utf-8", errors="ignore"):
                if not line.strip():
                    if physical_id or core_id:
                        pairs.add((physical_id, core_id))
                    physical_id = ""
                    core_id = ""
                elif line.startswith("physical id"):
                    physical_id = line.split(":", 1)[1].strip()
                elif line.startswith("core id"):
                    core_id = line.split(":", 1)[1].strip()
            if physical_id or core_id:
                pairs.add((physical_id, core_id))
            if pairs:
                return len(pairs)
        except OSError:
            pass
    elif system == "Darwin":
        try:
            value = subprocess.run(
                ["sysctl", "-n", "hw.physicalcpu"],
                capture_output=True,
                text=True,
                check=True,
                timeout=2,
            ).stdout.strip()
            if value.isdigit() and int(value) > 0:
                return int(value)
        except (OSError, subprocess.SubprocessError):
            pass

    logical = os.cpu_count() or 1
    return max(1, logical // 2 if logical > 1 else logical)


@dataclass(frozen=True)
class STTBackendEvaluation:
    backend: str
    model_format: str
    cache_namespace: str
    runtime: str
    acceleration: tuple[str, ...]
    timestamp_support: str
    packaging: str
    license: str
    status: Literal["adopted", "optional-benchmark", "excluded"]
    reason: str

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["acceleration"] = list(self.acceleration)
        return value


STT_BACKEND_EVALUATIONS = (
    STTBackendEvaluation(
        backend="faster-whisper",
        model_format="CTranslate2",
        cache_namespace="whisper/ctranslate2",
        runtime="Python add-on worker",
        acceleration=("CPU int8", "NVIDIA CUDA float16/int8_float16"),
        timestamp_support="segment and optional word timestamps",
        packaging="PyPI add-on; CUDA libraries remain environment-provided",
        license="MIT code; OpenAI Whisper weights use MIT",
        status="adopted",
        reason="Current provider with stable metadata, VAD, batching, and worker isolation.",
    ),
    STTBackendEvaluation(
        backend="whisper.cpp",
        model_format="GGML/GGUF plus optional Core ML/OpenVINO encoder",
        cache_namespace="whisper-cpp/ggml",
        runtime="native executable or server",
        acceleration=(
            "Apple Metal/Core ML",
            "Intel OpenVINO",
            "Vulkan",
            "NVIDIA CUDA",
            "AMD ROCm",
        ),
        timestamp_support="segment timestamps; word timing depends on binding/output",
        packaging="Separate native build matrix and model conversion/cache",
        license="MIT",
        status="optional-benchmark",
        reason="Promising cross-platform backend, but substantially expands native packaging.",
    ),
    STTBackendEvaluation(
        backend="mlx-whisper",
        model_format="MLX weights.npz/config.json",
        cache_namespace="mlx-whisper",
        runtime="macOS Apple-Silicon Python add-on",
        acceleration=("Apple Metal",),
        timestamp_support="segment and optional word timestamps",
        packaging="macOS-only Python add-on and separate converted model cache",
        license="MIT code; model license follows source Whisper checkpoint",
        status="optional-benchmark",
        reason="Apple-Silicon candidate; cannot be validated on Windows CI or bundled universally.",
    ),
    STTBackendEvaluation(
        backend="sensevoice-small",
        model_format="PyTorch or exported ONNX",
        cache_namespace="sensevoice",
        runtime="FunASR/PyTorch or ONNX worker",
        acceleration=("CPU", "CUDA", "ONNX Runtime"),
        timestamp_support="CTC-alignment timestamps",
        packaging="About 944 MB weights plus a separate runtime",
        license="FunASR model license; attribution and retained model name required",
        status="optional-benchmark",
        reason="Korean-capable low-latency candidate; model-license obligations need release notices.",
    ),
    STTBackendEvaluation(
        backend="qwen3-asr-0.6b",
        model_format="Safetensors",
        cache_namespace="qwen3-asr",
        runtime="PyTorch/Transformers or vLLM worker",
        acceleration=("CUDA",),
        timestamp_support="forced-aligner timestamp prediction",
        packaging="About 1.88 GB weights plus PyTorch/Transformers; GPU-oriented",
        license="Apache-2.0",
        status="optional-benchmark",
        reason="Korean accuracy candidate, but too heavy for the default lightweight runtime.",
    ),
    STTBackendEvaluation(
        backend="moonshine-ko",
        model_format="Moonshine checkpoint",
        cache_namespace="moonshine",
        runtime="separate Moonshine worker",
        acceleration=("CPU",),
        timestamp_support="provider-dependent",
        packaging="Small language-specific checkpoint and runtime",
        license="Moonshine AI Community License with attribution/display conditions",
        status="optional-benchmark",
        reason="Latency candidate only; license and timestamp contract require additional review.",
    ),
    STTBackendEvaluation(
        backend="distil-whisper",
        model_format="Transformers/CTranslate2 conversion",
        cache_namespace="distil-whisper",
        runtime="Python add-on worker",
        acceleration=("CPU", "CUDA"),
        timestamp_support="Whisper-compatible",
        packaging="Separate converted weights",
        license="MIT",
        status="excluded",
        reason="Official checkpoints are English-focused, so they are not Korean defaults.",
    ),
)


def backend_evaluation_report() -> list[dict[str, object]]:
    return [evaluation.to_dict() for evaluation in STT_BACKEND_EVALUATIONS]
