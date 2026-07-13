from __future__ import annotations

from pathlib import Path

from lecture_auto.local_runtime import LocalRuntimeManager, LocalRuntimeMissingError, RuntimeProgress
from lecture_auto.model_manager import default_model_dir
from lecture_auto.stt_config import STTConfig
from lecture_auto.stt_runtime import DiarizedSegment, STTConfigError, STTResult
from lecture_auto.tasking import CancellationToken


class WorkerWhisperSTTRuntimeAdapter:
    """STT adapter that never imports local-AI packages in the application process."""

    def __init__(
        self,
        config: STTConfig,
        runtime_manager: LocalRuntimeManager,
        *,
        progress: RuntimeProgress | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        self.config = config
        self.runtime_manager = runtime_manager
        self.progress = progress
        self.cancellation_token = cancellation_token

    def transcribe(self, *, audio_path: str) -> STTResult:
        if not audio_path.strip():
            raise STTConfigError("Audio path is required for transcription.")
        model = self.config.local_model_name or "base"
        model_root = default_model_dir() / "whisper"
        legacy_model_path = model_root / model
        try:
            result = self.runtime_manager.run_feature(
                "whisper",
                {
                "action": "whisper",
                "audio_path": str(Path(audio_path).resolve()),
                "model": model,
                "model_path": str(legacy_model_path) if legacy_model_path.is_dir() else None,
                "download_root": str(model_root),
                "language": self.config.language,
                "compute_type": "int8",
                },
                progress=self.progress,
                cancellation_token=self.cancellation_token,
                timeout=None,
            )
        except LocalRuntimeMissingError as exc:
            raise STTConfigError(
                "Whisper runtime is not installed. Open Settings > Local AI or run "
                "'lecture-auto runtime install --feature whisper'."
            ) from exc
        segments = [
            DiarizedSegment(
                speaker=str(value.get("speaker") or "Speaker 1"),
                start_time=float(value.get("start_time") or 0),
                end_time=float(value.get("end_time") or 0),
                text=str(value.get("text") or ""),
            )
            for value in result.get("segments", [])
            if isinstance(value, dict)
        ]
        return STTResult(
            transcript_text=str(result.get("transcript_text") or ""),
            provider="faster-whisper-worker",
            mode="local",
            language=result.get("language"),
            segments=segments,
        )
