from __future__ import annotations

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
