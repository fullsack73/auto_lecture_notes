from __future__ import annotations

from pathlib import Path

from lecture_auto.local_runtime import (
    LocalRuntimeError,
    LocalRuntimeManager,
    LocalRuntimeMissingError,
    RuntimeProgress,
)
from lecture_auto.model_manager import default_model_dir
from lecture_auto.stt_config import STTConfig
from lecture_auto.stt_runtime import (
    DiarizedSegment,
    STTConfigError,
    STTResult,
    STTRuntimeError,
    WordTimestamp,
)
from lecture_auto.stt_quality import assess_stt_quality
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
                    "device": self.config.local_device,
                    "compute_type": self.config.compute_type,
                    "batch_size": self.config.batch_size,
                    "beam_size": self.config.beam_size,
                    "temperature": self.config.temperature,
                    "vad_filter": self.config.vad_filter,
                    "vad_min_silence_duration_ms": self.config.vad_min_silence_duration_ms,
                    "condition_on_previous_text": self.config.condition_on_previous_text,
                    "word_timestamps": self.config.word_timestamps,
                    "hotwords": self.config.hotwords,
                    "cpu_threads": self.config.cpu_threads,
                    "num_workers": self.config.num_workers,
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
        except LocalRuntimeError as exc:
            raise STTRuntimeError(str(exc)) from exc
        segments = [
            DiarizedSegment(
                speaker=str(value.get("speaker") or "Speaker 1"),
                start_time=float(value.get("start_time") or 0),
                end_time=float(value.get("end_time") or 0),
                text=str(value.get("text") or ""),
                avg_logprob=_optional_float(value.get("avg_logprob")),
                compression_ratio=_optional_float(value.get("compression_ratio")),
                no_speech_prob=_optional_float(value.get("no_speech_prob")),
                temperature=_optional_float(value.get("temperature")),
                words=[
                    WordTimestamp(
                        word=str(word.get("word") or ""),
                        start_time=float(word.get("start_time") or 0),
                        end_time=float(word.get("end_time") or 0),
                        probability=_optional_float(word.get("probability")),
                    )
                    for word in value.get("words", [])
                    if isinstance(word, dict)
                ],
            )
            for value in result.get("segments", [])
            if isinstance(value, dict)
        ]
        metadata = dict(result.get("metadata") or {})
        metadata["quality"] = assess_stt_quality(segments)
        return STTResult(
            transcript_text=str(result.get("transcript_text") or ""),
            provider="faster-whisper-worker",
            mode="local",
            language=result.get("language"),
            segments=segments,
            metadata=metadata,
        )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
