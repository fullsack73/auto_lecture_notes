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
