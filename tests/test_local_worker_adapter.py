import pytest

from lecture_auto.local_runtime import LocalRuntimeError, LocalRuntimeMissingError
from lecture_auto.local_worker_adapter import WorkerWhisperSTTRuntimeAdapter
from lecture_auto.stt_config import STTConfig
from lecture_auto.stt_runtime import STTConfigError, STTRuntimeError


class FailingRuntime:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def run_feature(self, *_args, **_kwargs):
        raise self.error


def test_worker_adapter_maps_missing_runtime_to_config_error() -> None:
    adapter = WorkerWhisperSTTRuntimeAdapter(
        STTConfig(mode="local"),
        FailingRuntime(LocalRuntimeMissingError("whisper")),  # type: ignore[arg-type]
    )

    with pytest.raises(STTConfigError, match="not installed"):
        adapter.transcribe(audio_path="lecture.wav")


def test_worker_adapter_maps_worker_failure_to_stt_runtime_error() -> None:
    adapter = WorkerWhisperSTTRuntimeAdapter(
        STTConfig(mode="local"),
        FailingRuntime(LocalRuntimeError("CUDA initialization failed")),  # type: ignore[arg-type]
    )

    with pytest.raises(STTRuntimeError, match="CUDA initialization failed"):
        adapter.transcribe(audio_path="lecture.wav")
