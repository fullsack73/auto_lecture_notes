from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

STTMode = Literal["local", "api"]
STTDevice = Literal["auto", "cpu", "cuda"]

SUPPORTED_API_PROVIDERS = {"openai-compatible", "deepgram"}
SUPPORTED_LOCAL_DEVICES = {"auto", "cpu", "cuda"}
SUPPORTED_COMPUTE_TYPES = {
    "auto",
    "int8",
    "int8_float16",
    "int8_float32",
    "float16",
    "float32",
    "bfloat16",
}
LOCAL_MODEL_RECOMMENDATIONS = (
    ("base", "저사양 CPU·RAM 8GB 이하 / 빠른 초안"),
    ("small", "CPU·Apple Silicon 기본 권장 / NVIDIA VRAM 4~6GB"),
    ("medium", "NVIDIA VRAM 8~12GB / 정확도·속도 균형"),
    ("large-v3", "NVIDIA VRAM 16GB 이상 / 정확도 우선"),
)

LOCAL_STT_HARDWARE_GUIDE = (
    "권장값(자동 적용 아님): CPU·Apple Silicon → small/cpu/int8 · "
    "NVIDIA 4~6GB → small/cuda/int8_float16 · "
    "NVIDIA 8~12GB → medium/cuda/float16 · "
    "NVIDIA 16GB+ → large-v3/cuda/float16 · "
    "AMD·Intel GPU → 현재 small/cpu/int8"
)


@dataclass
class STTConfig:
    """Configuration contract for selecting STT mode and provider options."""

    mode: STTMode = "api"
    api_provider: str | None = "openai-compatible"
    api_key: str | None = None
    local_model_name: str | None = "base"
    language: str | None = None
    diarization: bool = False
    local_device: STTDevice = "cpu"
    compute_type: str = "int8"
    batch_size: int = 1
    beam_size: int = 5
    temperature: float | None = None
    vad_filter: bool = False
    vad_min_silence_duration_ms: int = 2000
    condition_on_previous_text: bool = True
    word_timestamps: bool = False
    hotwords: str | None = None
    cpu_threads: int = 0
    num_workers: int = 1
    use_dynaudnorm: bool = False
    dynaudnorm_f: int | None = None
    dynaudnorm_g: int | None = None
    gain_db: float | None = None


    def validate(self) -> None:
        if self.mode not in {"local", "api"}:
            raise ValueError("Unsupported STT mode. Use 'local' or 'api'.")

        if self.mode == "api":
            if not self.api_provider or not self.api_provider.strip():
                raise ValueError("API provider is required when STT mode is 'api'.")
            if not self.api_key or not self.api_key.strip():
                raise ValueError("API key is required when STT mode is 'api'.")

        if self.mode == "local":
            if not self.local_model_name or not self.local_model_name.strip():
                raise ValueError("Local model name is required when STT mode is 'local'.")
            if self.local_device not in SUPPORTED_LOCAL_DEVICES:
                raise ValueError(
                    f"Unsupported local STT device. Use one of {sorted(SUPPORTED_LOCAL_DEVICES)}."
                )
            if self.compute_type not in SUPPORTED_COMPUTE_TYPES:
                raise ValueError(
                    f"Unsupported local STT compute type. Use one of {sorted(SUPPORTED_COMPUTE_TYPES)}."
                )
            if self.batch_size < 1 or self.batch_size > 64:
                raise ValueError("STT batch_size must be between 1 and 64.")
            if self.batch_size > 1 and not self.vad_filter:
                raise ValueError("STT batched transcription requires vad_filter to be enabled.")
            if self.beam_size < 1 or self.beam_size > 20:
                raise ValueError("STT beam_size must be between 1 and 20.")
            if self.temperature is not None and not 0.0 <= self.temperature <= 1.0:
                raise ValueError("STT temperature must be between 0.0 and 1.0.")
            if not 0 <= self.vad_min_silence_duration_ms <= 10000:
                raise ValueError(
                    "STT vad_min_silence_duration_ms must be between 0 and 10000."
                )
            if self.cpu_threads < 0 or self.cpu_threads > 256:
                raise ValueError("STT cpu_threads must be between 0 and 256.")
            if self.num_workers < 1 or self.num_workers > 16:
                raise ValueError("STT num_workers must be between 1 and 16.")

        if self.dynaudnorm_f is not None and (self.dynaudnorm_f < 10 or self.dynaudnorm_f > 8000):
            raise ValueError("dynaudnorm_f must be between 10 and 8000.")
        if self.dynaudnorm_g is not None and (self.dynaudnorm_g < 3 or self.dynaudnorm_g > 301 or self.dynaudnorm_g % 2 == 0):
            raise ValueError("dynaudnorm_g must be an odd integer between 3 and 301.")
        if self.gain_db is not None and (self.gain_db < -60.0 or self.gain_db > 60.0):
            raise ValueError("gain_db must be between -60.0 and 60.0.")
