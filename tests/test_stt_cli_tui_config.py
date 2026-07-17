from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from lecture_auto.cli import _build_service, app
from lecture_auto.tui import _menu_config, _select_llm_model, _select_llm_provider


runner = CliRunner()


def _config_path(home_dir: Path) -> Path:
    return home_dir / ".lecture_auto" / "config.json"


def _set_test_home(monkeypatch, home_dir: Path) -> None:
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))


def test_cli_config_set_persists_stt_mode_and_local_model(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)

    result = runner.invoke(
        app,
        ["config", "set", "--stt-mode", "local", "--stt-local-model", "large-v3"],
    )

    assert result.exit_code == 0
    config_data = json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))
    assert config_data["stt_mode"] == "local"
    assert config_data["stt_local_model"] == "large-v3"


def test_cli_config_set_rejects_invalid_stt_mode(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)

    result = runner.invoke(app, ["config", "set", "--stt-mode", "invalid"])

    assert result.exit_code == 1
    assert "STT mode must be 'api' or 'local'." in (result.output or "")


def test_cli_config_set_rejects_unsupported_stt_api_provider(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)

    result = runner.invoke(app, ["config", "set", "--stt-api-provider", "unsupported-provider"])

    assert result.exit_code == 1
    assert "STT API provider must be one of" in (result.output or "")
    assert not _config_path(tmp_path).exists()


def test_cli_config_set_normalizes_deprecated_gemini_flash_lite_model(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)

    result = runner.invoke(
        app,
        ["config", "set", "--llm-model", "gemini-3.1-flash-lite-preview"],
    )

    assert result.exit_code == 0
    config_data = json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))
    assert config_data["llm_model_name"] == "gemini-3.1-flash-lite"


def test_cli_config_set_accepts_google_api_gemma4_model(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)

    result = runner.invoke(
        app,
        ["config", "set", "--llm-model", "gemma-4-26b-a4b-it"],
    )

    assert result.exit_code == 0
    config_data = json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))
    assert config_data["llm_model_name"] == "gemma-4-26b-a4b-it"


def test_build_service_loads_stt_mode_and_local_model_from_config(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.delenv("STT_MODE", raising=False)
    monkeypatch.delenv("STT_LOCAL_MODEL", raising=False)

    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"stt_mode": "local", "stt_local_model": "medium"}),
        encoding="utf-8",
    )

    service = _build_service()

    assert service.stt_config.mode == "local"
    assert service.stt_config.local_model_name == "medium"


def test_build_service_env_overrides_config_for_stt_mode_and_model(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.setenv("STT_MODE", "api")
    monkeypatch.setenv("STT_LOCAL_MODEL", "base")

    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"stt_mode": "local", "stt_local_model": "large-v3"}),
        encoding="utf-8",
    )

    service = _build_service()

    assert service.stt_config.mode == "api"
    assert service.stt_config.local_model_name == "base"


def test_build_service_loads_llm_model_and_thinking_from_config(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_THINKING_LEVEL", raising=False)

    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "gemini_api_key": "fake-key",
                "llm_model_name": "gemini-3.1-pro-preview",
                "llm_thinking_level": "high",
            }
        ),
        encoding="utf-8",
    )

    with patch("lecture_auto.cli.GeminiLLMAdapter") as adapter_cls:
        service = _build_service()

    assert service.llm_adapter is adapter_cls.return_value
    used_config = adapter_cls.call_args.args[0]
    assert used_config.model_name == "gemini-3.1-pro-preview"
    assert used_config.thinking_level == "high"


def test_build_service_env_overrides_llm_model_and_thinking(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_MODEL", "gemini-3.1-flash-lite-preview")
    monkeypatch.setenv("LLM_THINKING_LEVEL", "low")

    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "gemini_api_key": "fake-key",
                "llm_model_name": "gemini-3.1-pro-preview",
                "llm_thinking_level": "high",
            }
        ),
        encoding="utf-8",
    )

    with patch("lecture_auto.cli.GeminiLLMAdapter") as adapter_cls:
        service = _build_service()

    assert service.llm_adapter is adapter_cls.return_value
    used_config = adapter_cls.call_args.args[0]
    assert used_config.model_name == "gemini-3.1-flash-lite"
    assert used_config.thinking_level == "low"


def test_build_service_loads_local_llm_provider_alias_from_config(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "llm_provider": "local",
                "llm_model_name": "gemma4:31b-cloud",
                "llm_thinking_level": "medium",
            }
        ),
        encoding="utf-8",
    )

    with patch("lecture_auto.cli.OllamaLLMAdapter") as adapter_cls:
        service = _build_service()

    assert service.llm_adapter is adapter_cls.return_value
    used_config = adapter_cls.call_args.args[0]
    assert used_config.provider == "ollama"
    assert used_config.model_name == "gemma4:31b-cloud"


def test_build_service_loads_google_api_llm_provider_alias_from_config(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "llm_provider": "google api",
                "gemini_api_key": "fake-key",
                "llm_model_name": "gemma-4-31b-it",
            }
        ),
        encoding="utf-8",
    )

    with patch("lecture_auto.cli.GeminiLLMAdapter") as adapter_cls:
        service = _build_service()

    assert service.llm_adapter is adapter_cls.return_value
    used_config = adapter_cls.call_args.args[0]
    assert used_config.provider == "gemini"
    assert used_config.model_name == "gemma-4-31b-it"


def test_cli_config_set_persists_dynaudnorm(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)

    result = runner.invoke(app, ["config", "set", "--dynaudnorm-f", "200"])

    assert result.exit_code == 0
    config_data = json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))
    assert config_data["dynaudnorm_f"] == 200


def test_cli_config_set_rejects_out_of_range_dynaudnorm_f(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)

    result = runner.invoke(app, ["config", "set", "--dynaudnorm-f", "5"])

    assert result.exit_code == 1
    assert "dynaudnorm_f must be between 10 and 8000" in (result.output or "")


def test_build_service_loads_dynaudnorm_from_config(tmp_path: Path, monkeypatch) -> None:
    _set_test_home(monkeypatch, tmp_path)

    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"use_dynaudnorm": True, "dynaudnorm_f": 100}),
        encoding="utf-8",
    )

    service = _build_service()

    assert service.stt_config.use_dynaudnorm is True
    assert service.stt_config.dynaudnorm_f == 100


def test_tui_menu_config_saves_dynaudnorm(monkeypatch) -> None:
    saved: dict = {}

    def _save(data: dict) -> None:
        saved.clear()
        saved.update(data)

    with patch("lecture_auto.tui._load_config", return_value={}):
        with patch("lecture_auto.tui._save_config", side_effect=_save):
            with patch(
                "lecture_auto.tui._select",
                side_effect=["set", "use_dynaudnorm", "__save__", "__back__"],
            ):
                with patch("lecture_auto.tui._ask", return_value="True"):
                    changed = _menu_config()

    assert changed is True
    assert saved["use_dynaudnorm"] is True


def test_tui_menu_config_saves_stt_mode(monkeypatch) -> None:
    saved: dict = {}

    def _save(data: dict) -> None:
        saved.clear()
        saved.update(data)

    with patch("lecture_auto.tui._load_config", return_value={}):
        with patch("lecture_auto.tui._save_config", side_effect=_save):
            with patch(
                "lecture_auto.tui._select",
                side_effect=["set", "stt_mode", "__save__", "__back__"],
            ):
                with patch("lecture_auto.tui._select_stt_mode", return_value="local"):
                    changed = _menu_config()

    assert changed is True
    assert saved["stt_mode"] == "local"


def test_tui_menu_config_saves_stt_local_model(monkeypatch) -> None:
    saved: dict = {}

    def _save(data: dict) -> None:
        saved.clear()
        saved.update(data)

    with patch("lecture_auto.tui._load_config", return_value={}):
        with patch("lecture_auto.tui._save_config", side_effect=_save):
            with patch(
                "lecture_auto.tui._select",
                side_effect=["set", "stt_local_model", "__save__", "__back__"],
            ):
                with patch(
                    "lecture_auto.tui._select_stt_local_model",
                    return_value="distil-large-v3",
                ):
                    changed = _menu_config()

    assert changed is True
    assert saved["stt_local_model"] == "distil-large-v3"


def test_tui_menu_config_saves_llm_provider(monkeypatch) -> None:
    saved: dict = {}

    def _save(data: dict) -> None:
        saved.clear()
        saved.update(data)

    with patch("lecture_auto.tui._load_config", return_value={}):
        with patch("lecture_auto.tui._save_config", side_effect=_save):
            with patch(
                "lecture_auto.tui._select",
                side_effect=["set", "llm_provider", "__save__", "__back__"],
            ):
                with patch("lecture_auto.tui._select_llm_provider", return_value="local"):
                    changed = _menu_config()

    assert changed is True
    assert saved["llm_provider"] == "local"


def test_tui_llm_provider_uses_google_api_label() -> None:
    captured_choices = []

    def _capture_select(_prompt: str, choices: list) -> str:
        captured_choices.extend(choices)
        return "gemini"

    with patch("lecture_auto.tui._select", side_effect=_capture_select):
        result = _select_llm_provider()

    assert result == "gemini"
    assert any(getattr(choice, "title", "") == "Google API" for choice in captured_choices)


def test_tui_llm_model_includes_gemma4_google_api_options() -> None:
    captured_choices = []

    def _capture_select(_prompt: str, choices: list) -> str:
        captured_choices.extend(choices)
        return "gemma-4-31b-it"

    with patch("lecture_auto.tui._select", side_effect=_capture_select):
        result = _select_llm_model(provider="gemini", current="gemma-4-31b-it")

    titles = [getattr(choice, "title", "") for choice in captured_choices]
    values = [getattr(choice, "value", "") for choice in captured_choices]

    assert result == "gemma-4-31b-it"
    assert "Gemma 4 26B (Google API)" in titles
    assert "Gemma 4 31B (Google API)" in titles
    assert "gemma-4-26b-a4b-it" in values
    assert "gemma-4-31b-it" in values
