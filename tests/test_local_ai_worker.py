from __future__ import annotations

import sys
from types import SimpleNamespace

import lecture_auto.local_ai_worker as worker


def test_package_probe_treats_missing_parent_module_as_not_found(monkeypatch) -> None:
    def missing_parent(_module_name: str):
        raise ModuleNotFoundError("No module named 'google'")

    monkeypatch.setattr(worker.importlib.util, "find_spec", missing_parent)

    result = worker.package_probe("google_genai", "google.genai")

    assert result == {
        "found": False,
        "import_ok": False,
        "version": None,
        "error": None,
    }


def test_whisper_forces_cpu_device(monkeypatch, tmp_path) -> None:
    created: dict[str, object] = {}

    class FakeWhisperModel:
        def __init__(self, model_source, **kwargs) -> None:
            created["model_source"] = model_source
            created["kwargs"] = kwargs

        def transcribe(self, _audio_path, **_kwargs):
            segment = SimpleNamespace(text=" hello ", start=0.0, end=0.5)
            info = SimpleNamespace(duration=0.5, language="en")
            return [segment], info

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )

    result = worker.whisper(
        {
            "audio_path": str(tmp_path / "audio.wav"),
            "model": "base",
            "compute_type": "int8",
        }
    )

    assert created["kwargs"] == {"device": "cpu", "compute_type": "int8"}
    assert result["transcript_text"] == "hello"


def test_whisper_uses_auto_cuda_batch_vad_and_preserves_confidence(
    monkeypatch, tmp_path
) -> None:
    created: dict[str, object] = {}

    class FakeWhisperModel:
        def __init__(self, model_source, **kwargs) -> None:
            created["model_source"] = model_source
            created["kwargs"] = kwargs

    class FakeBatchedInferencePipeline:
        def __init__(self, model) -> None:
            created["batched_model"] = model

        def transcribe(self, _audio_path, **kwargs):
            created["transcribe_kwargs"] = kwargs
            word = SimpleNamespace(
                word=" 테스트",
                start=0.1,
                end=0.4,
                probability=0.91,
            )
            segment = SimpleNamespace(
                text=" 테스트 ",
                start=0.0,
                end=0.5,
                avg_logprob=-0.25,
                compression_ratio=1.2,
                no_speech_prob=0.05,
                temperature=0.0,
                words=[word],
            )
            info = SimpleNamespace(
                duration=0.5,
                duration_after_vad=0.45,
                language="ko",
                language_probability=0.99,
            )
            return [segment], info

    fake_faster_whisper = SimpleNamespace(
        WhisperModel=FakeWhisperModel,
        BatchedInferencePipeline=FakeBatchedInferencePipeline,
    )
    fake_ctranslate2 = SimpleNamespace(
        get_cuda_device_count=lambda: 1,
        get_supported_compute_types=lambda _device: {"float16", "int8_float16"},
    )
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_faster_whisper)
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ctranslate2)

    result = worker.whisper(
        {
            "audio_path": str(tmp_path / "audio.wav"),
            "model": "base",
            "device": "auto",
            "compute_type": "auto",
            "batch_size": 4,
            "beam_size": 1,
            "temperature": 0.0,
            "vad_filter": True,
            "vad_min_silence_duration_ms": 1000,
            "condition_on_previous_text": False,
            "word_timestamps": True,
            "hotwords": "테스트",
        }
    )

    assert created["kwargs"] == {"device": "cuda", "compute_type": "float16"}
    assert created["transcribe_kwargs"] == {
        "beam_size": 1,
        "temperature": 0.0,
        "vad_filter": True,
        "vad_parameters": {"min_silence_duration_ms": 1000},
        "condition_on_previous_text": False,
        "word_timestamps": True,
        "hotwords": "테스트",
        "batch_size": 4,
    }
    assert result["segments"][0]["avg_logprob"] == -0.25
    assert result["segments"][0]["words"][0]["probability"] == 0.91
    assert result["metadata"]["device"] == "cuda"
    assert result["metadata"]["duration_after_vad_seconds"] == 0.45


def test_whisper_retries_smaller_batch_after_memory_error(
    monkeypatch, tmp_path
) -> None:
    attempted_batches: list[int] = []

    class FakeWhisperModel:
        def __init__(self, _model_source, **_kwargs) -> None:
            pass

    class FakeBatchedInferencePipeline:
        def __init__(self, model) -> None:
            pass

        def transcribe(self, _audio_path, **kwargs):
            batch_size = kwargs["batch_size"]
            attempted_batches.append(batch_size)
            if batch_size == 4:
                raise RuntimeError("CUDA out of memory")
            segment = SimpleNamespace(text=" 성공 ", start=0.0, end=1.0)
            return [segment], SimpleNamespace(duration=1.0, language="ko")

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(
            WhisperModel=FakeWhisperModel,
            BatchedInferencePipeline=FakeBatchedInferencePipeline,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        SimpleNamespace(
            get_cuda_device_count=lambda: 0,
            get_supported_compute_types=lambda _device: {"int8", "float32"},
        ),
    )

    result = worker.whisper(
        {
            "audio_path": str(tmp_path / "audio.wav"),
            "model": "base",
            "device": "cpu",
            "compute_type": "int8",
            "batch_size": 4,
            "vad_filter": True,
        }
    )

    assert attempted_batches == [4, 2]
    assert result["transcript_text"] == "성공"
    assert result["metadata"]["requested_batch_size"] == 4
    assert result["metadata"]["batch_size"] == 2
    assert result["metadata"]["batch_retry_count"] == 1
