from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from lecture_auto.llm_config import DEFAULT_GEMINI_MODEL, LLMConfig, normalize_gemini_model_name
from lecture_auto.stt_config import STTConfig

if TYPE_CHECKING:
    from lecture_auto.library_service import LibraryService
    from lecture_auto.local_runtime import LocalRuntimeManager
    from lecture_auto.model_manager import ModelManager
    from lecture_auto.session_service import SessionService


SECRET_SERVICE = "lecture-auto"
SECRET_FIELDS = ("stt_api_key", "gemini_api_key")
WORKSPACE_DIRECTORIES = ("metadata", "recordings", "transcripts", "notes", "materials")


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...


class KeyringSecretStore:
    _fallback: dict[str, str] = {}

    @staticmethod
    def _system_store_available() -> bool:
        if sys.platform == "darwin":
            return (Path.home() / "Library" / "Keychains" / "login.keychain-db").exists()
        return True

    def get(self, name: str) -> str | None:
        if not self._system_store_available():
            return self._fallback.get(name)
        try:
            import keyring
            return keyring.get_password(SECRET_SERVICE, name) or self._fallback.get(name)
        except Exception:
            return self._fallback.get(name)

    def set(self, name: str, value: str) -> None:
        if not self._system_store_available():
            self._fallback[name] = value
            return
        try:
            import keyring
            keyring.set_password(SECRET_SERVICE, name, value)
        except Exception:
            self._fallback[name] = value

    def delete(self, name: str) -> None:
        if not self._system_store_available():
            self._fallback.pop(name, None)
            return
        try:
            import keyring
            keyring.delete_password(SECRET_SERVICE, name)
        except Exception:
            self._fallback.pop(name, None)


@dataclass
class AppConfig:
    workspace: Path
    ui_language: str = "ko"
    audio_format: str = "wav"
    capture_source: str = "microphone"
    capture_device_id: str | None = None
    capture_device_name: str | None = None
    capture_backend: str | None = None
    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=lambda: LLMConfig(api_key=None))

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace).expanduser().resolve()


class ConfigRepository:
    def __init__(self, path: Path | None = None, secret_store: SecretStore | None = None) -> None:
        self.path = path or Path.home() / ".lecture_auto" / "config.json"
        self.secret_store = secret_store or KeyringSecretStore()

    def exists(self) -> bool:
        return self.path.exists()

    def load(self, *, load_secrets: bool = True) -> AppConfig:
        data = self._read_raw()
        self._migrate_plaintext_secrets(data)

        workspace_raw = os.environ.get("LECTURE_AUTO_WORKSPACE") or data.get("workspace")
        workspace = Path(workspace_raw) if workspace_raw else Path.home() / ".lecture_auto"
        stt_mode = os.environ.get("STT_MODE") or data.get("stt_mode") or "api"
        stt_api_key = os.environ.get("STT_API_KEY")
        if load_secrets and not stt_api_key and stt_mode == "api":
            stt_api_key = self.get_secret("stt_api_key")

        stt = STTConfig(
            mode=stt_mode,  # type: ignore[arg-type]
            api_provider=os.environ.get("STT_API_PROVIDER") or data.get("stt_api_provider") or "openai-compatible",
            api_key=stt_api_key,
            local_model_name=os.environ.get("STT_LOCAL_MODEL") or data.get("stt_local_model") or "base",
            language=data.get("stt_language"),
            local_device=str(
                os.environ.get("STT_LOCAL_DEVICE")
                or data.get("stt_local_device")
                or "cpu"
            ),  # type: ignore[arg-type]
            compute_type=str(
                os.environ.get("STT_COMPUTE_TYPE")
                or data.get("stt_compute_type")
                or "int8"
            ),
            batch_size=self._optional_int(
                os.environ["STT_BATCH_SIZE"]
                if "STT_BATCH_SIZE" in os.environ
                else data.get("stt_batch_size")
            ) or 1,
            beam_size=self._optional_int(
                os.environ["STT_BEAM_SIZE"]
                if "STT_BEAM_SIZE" in os.environ
                else data.get("stt_beam_size")
            ) or 5,
            temperature=self._optional_float(
                os.environ["STT_TEMPERATURE"]
                if "STT_TEMPERATURE" in os.environ
                else data.get("stt_temperature")
            ),
            vad_filter=self._env_bool(
                "STT_VAD_FILTER", data.get("stt_vad_filter", False)
            ),
            vad_min_silence_duration_ms=self._optional_int(
                os.environ["STT_VAD_MIN_SILENCE_MS"]
                if "STT_VAD_MIN_SILENCE_MS" in os.environ
                else data.get("stt_vad_min_silence_duration_ms", 2000)
            ) or 0,
            condition_on_previous_text=self._env_bool(
                "STT_CONDITION_ON_PREVIOUS_TEXT",
                data.get("stt_condition_on_previous_text", True),
            ),
            word_timestamps=self._env_bool(
                "STT_WORD_TIMESTAMPS", data.get("stt_word_timestamps", False)
            ),
            hotwords=(
                os.environ.get("STT_HOTWORDS")
                or data.get("stt_hotwords")
                or None
            ),
            cpu_threads=self._optional_int(
                os.environ["STT_CPU_THREADS"]
                if "STT_CPU_THREADS" in os.environ
                else data.get("stt_cpu_threads")
            ) or 0,
            num_workers=self._optional_int(
                os.environ["STT_NUM_WORKERS"]
                if "STT_NUM_WORKERS" in os.environ
                else data.get("stt_num_workers")
            ) or 1,
            quality_retry_enabled=self._env_bool(
                "STT_QUALITY_RETRY",
                data.get("stt_quality_retry_enabled", True),
            ),
            quality_retry_model=(
                os.environ.get("STT_QUALITY_RETRY_MODEL")
                or data.get("stt_quality_retry_model")
                or None
            ),
            quality_retry_beam_size=self._optional_int(
                os.environ["STT_QUALITY_RETRY_BEAM_SIZE"]
                if "STT_QUALITY_RETRY_BEAM_SIZE" in os.environ
                else data.get("stt_quality_retry_beam_size", 5)
            ) or 5,
            quality_retry_context_seconds=self._optional_float(
                os.environ["STT_QUALITY_RETRY_CONTEXT_SECONDS"]
                if "STT_QUALITY_RETRY_CONTEXT_SECONDS" in os.environ
                else data.get("stt_quality_retry_context_seconds", 1.5)
            ) or 0.0,
            quality_retry_max_windows=self._optional_int(
                os.environ["STT_QUALITY_RETRY_MAX_WINDOWS"]
                if "STT_QUALITY_RETRY_MAX_WINDOWS" in os.environ
                else data.get("stt_quality_retry_max_windows", 8)
            ) or 0,
            quality_retry_max_seconds=self._optional_float(
                os.environ["STT_QUALITY_RETRY_MAX_SECONDS"]
                if "STT_QUALITY_RETRY_MAX_SECONDS" in os.environ
                else data.get("stt_quality_retry_max_seconds", 120.0)
            ) or 0.0,
            use_dynaudnorm=self._env_bool("USE_DYNAUDNORM", data.get("use_dynaudnorm", False)),
            dynaudnorm_f=self._optional_int(data.get("dynaudnorm_f")),
            dynaudnorm_g=self._optional_int(data.get("dynaudnorm_g")),
            gain_db=self._optional_float(data.get("gain_db")),
        )
        provider = str(os.environ.get("LLM_PROVIDER") or data.get("llm_provider") or "gemini").lower()
        if provider in {"google", "google_api", "google-api", "google api"}:
            provider = "gemini"
        if provider == "local":
            provider = "ollama"
        gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if load_secrets and not gemini_api_key and provider == "gemini":
            gemini_api_key = self.get_secret("gemini_api_key")
        default_model = "gemma4:31b-cloud" if provider == "ollama" else DEFAULT_GEMINI_MODEL
        model_name = os.environ.get("LLM_MODEL") or data.get("llm_model_name") or default_model
        if provider == "gemini":
            model_name = normalize_gemini_model_name(str(model_name))
        llm = LLMConfig(
            provider=provider,
            api_key=gemini_api_key,
            model_name=str(model_name),
            thinking_level=str(os.environ.get("LLM_THINKING_LEVEL") or data.get("llm_thinking_level") or "medium"),
            language=data.get("llm_language"),
            ollama_base_url=str(data.get("ollama_base_url") or "http://localhost:11434"),
        )
        return AppConfig(
            workspace=workspace,
            ui_language=str(data.get("ui_language") or "ko"),
            audio_format=str(os.environ.get("LECTURE_AUTO_AUDIO_FORMAT") or data.get("audio_format") or "wav"),
            capture_source=str(os.environ.get("LECTURE_AUTO_CAPTURE_SOURCE") or data.get("capture_source") or "microphone"),
            capture_device_id=data.get("capture_device_id"),
            capture_device_name=data.get("capture_device_name"),
            capture_backend=data.get("capture_backend"),
            stt=stt,
            llm=llm,
        )

    def save(self, config: AppConfig) -> None:
        self._validate(config)
        data = {
            "config_version": 2,
            "workspace": str(config.workspace),
            "ui_language": config.ui_language,
            "audio_format": config.audio_format,
            "capture_source": config.capture_source,
            "capture_device_id": config.capture_device_id,
            "capture_device_name": config.capture_device_name,
            "capture_backend": config.capture_backend,
            "stt_mode": config.stt.mode,
            "stt_api_provider": config.stt.api_provider,
            "stt_local_model": config.stt.local_model_name,
            "stt_language": config.stt.language,
            "stt_local_device": config.stt.local_device,
            "stt_compute_type": config.stt.compute_type,
            "stt_batch_size": config.stt.batch_size,
            "stt_beam_size": config.stt.beam_size,
            "stt_temperature": config.stt.temperature,
            "stt_vad_filter": config.stt.vad_filter,
            "stt_vad_min_silence_duration_ms": config.stt.vad_min_silence_duration_ms,
            "stt_condition_on_previous_text": config.stt.condition_on_previous_text,
            "stt_word_timestamps": config.stt.word_timestamps,
            "stt_hotwords": config.stt.hotwords,
            "stt_cpu_threads": config.stt.cpu_threads,
            "stt_num_workers": config.stt.num_workers,
            "stt_quality_retry_enabled": config.stt.quality_retry_enabled,
            "stt_quality_retry_model": config.stt.quality_retry_model,
            "stt_quality_retry_beam_size": config.stt.quality_retry_beam_size,
            "stt_quality_retry_context_seconds": config.stt.quality_retry_context_seconds,
            "stt_quality_retry_max_windows": config.stt.quality_retry_max_windows,
            "stt_quality_retry_max_seconds": config.stt.quality_retry_max_seconds,
            "use_dynaudnorm": config.stt.use_dynaudnorm,
            "dynaudnorm_f": config.stt.dynaudnorm_f,
            "dynaudnorm_g": config.stt.dynaudnorm_g,
            "gain_db": config.stt.gain_db,
            "llm_provider": config.llm.provider,
            "llm_model_name": config.llm.model_name,
            "llm_thinking_level": config.llm.thinking_level,
            "llm_language": config.llm.language,
            "ollama_base_url": config.llm.ollama_base_url,
        }
        data = {key: value for key, value in data.items() if value is not None}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
        if config.stt.api_key:
            self.set_secret("stt_api_key", config.stt.api_key)
        if config.llm.api_key:
            self.set_secret("gemini_api_key", config.llm.api_key)

    def get_secret(self, name: str) -> str | None:
        if name not in SECRET_FIELDS:
            raise ValueError(f"Unknown secret field: {name}")
        return self.secret_store.get(name)

    def set_secret(self, name: str, value: str | None) -> None:
        if name not in SECRET_FIELDS:
            raise ValueError(f"Unknown secret field: {name}")
        if value and value.strip():
            self.secret_store.set(name, value.strip())
        else:
            self.secret_store.delete(name)

    def masked_dict(self) -> dict[str, object]:
        data = self._read_raw()
        for name in SECRET_FIELDS:
            if self.secret_store.get(name):
                data[name] = "********"
            else:
                data.pop(name, None)
        return data

    def _migrate_plaintext_secrets(self, data: dict[str, object]) -> None:
        changed = False
        for name in SECRET_FIELDS:
            value = data.pop(name, None)
            if isinstance(value, str) and value.strip():
                self.secret_store.set(name, value.strip())
                changed = True
        if changed:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_raw(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _validate(config: AppConfig) -> None:
        if config.audio_format not in {"wav", "mp3"}:
            raise ValueError("Audio format must be 'wav' or 'mp3'.")
        if config.capture_source not in {"microphone", "system_audio"}:
            raise ValueError("Capture source must be 'microphone' or 'system_audio'.")
        if config.ui_language not in {"ko", "en"}:
            raise ValueError("UI language must be 'ko' or 'en'.")

    @staticmethod
    def _optional_int(value: object) -> int | None:
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_float(value: object) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _env_bool(name: str, default: object) -> bool:
        value = os.environ.get(name)
        if value is None:
            return bool(default)
        return value.strip().lower() not in {"", "0", "false", "no", "off"}


@dataclass
class ServiceContainer:
    session: SessionService
    library: LibraryService
    models: ModelManager
    runtime: LocalRuntimeManager


def ensure_workspace_structure(workspace: Path) -> Path:
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for directory in WORKSPACE_DIRECTORIES:
        (root / directory).mkdir(exist_ok=True)
    return root


def build_service_container(
    config: AppConfig,
    *,
    gemini_adapter_cls=None,
    ollama_adapter_cls=None,
) -> ServiceContainer:
    from lecture_auto.capture_runtime import FFmpegCaptureRuntimeAdapter
    from lecture_auto.library_service import LibraryService
    from lecture_auto.llm_adapter import GeminiLLMAdapter, OllamaLLMAdapter
    from lecture_auto.local_runtime import LocalRuntimeManager
    from lecture_auto.model_manager import ModelManager
    from lecture_auto.session_metadata_store import SessionMetadataStore
    from lecture_auto.session_service import SessionService

    config.workspace = ensure_workspace_structure(config.workspace)
    os.environ["LECTURE_AUTO_WORKSPACE"] = str(config.workspace)
    store = SessionMetadataStore(config.workspace / "metadata" / "sessions.json")
    local_runtime = LocalRuntimeManager()
    custom_gemini_adapter = gemini_adapter_cls is not None and gemini_adapter_cls is not GeminiLLMAdapter
    gemini_adapter_cls = gemini_adapter_cls or GeminiLLMAdapter
    ollama_adapter_cls = ollama_adapter_cls or OllamaLLMAdapter
    llm_adapter = None
    if config.llm.provider == "gemini" and config.llm.api_key:
        if custom_gemini_adapter:
            llm_adapter = gemini_adapter_cls(config.llm)
        else:
            llm_adapter = gemini_adapter_cls(config.llm, runtime_manager=local_runtime)
    elif config.llm.provider == "ollama":
        llm_adapter = ollama_adapter_cls(config.llm)
    runtime = FFmpegCaptureRuntimeAdapter(
        capture_source=config.capture_source,
        device_id=config.capture_device_id,
        device_name=config.capture_device_name,
        backend=config.capture_backend,
    )
    session = SessionService(
        store=store,
        runtime_adapter=runtime,
        stt_config=config.stt,
        llm_adapter=llm_adapter,
        local_runtime_manager=local_runtime,
        audio_format=config.audio_format,
    )
    return ServiceContainer(
        session=session,
        library=LibraryService(store=store, base_dir=config.workspace),
        models=ModelManager(
            ollama_base_url=config.llm.ollama_base_url,
            local_runtime_manager=local_runtime,
        ),
        runtime=local_runtime,
    )
