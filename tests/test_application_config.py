from __future__ import annotations

import json
from pathlib import Path

from lecture_auto.application import AppConfig, ConfigRepository, KeyringSecretStore


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


def test_plaintext_secrets_migrate_out_of_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"workspace": str(tmp_path / "workspace"), "stt_api_key": "stt-secret", "gemini_api_key": "llm-secret"}),
        encoding="utf-8",
    )
    secrets = MemorySecretStore()

    config = ConfigRepository(path, secrets).load()

    assert config.stt.api_key == "stt-secret"
    assert config.llm.api_key == "llm-secret"
    assert "api_key" not in path.read_text(encoding="utf-8")
    assert secrets.values == {"stt_api_key": "stt-secret", "gemini_api_key": "llm-secret"}


def test_saved_config_keeps_secrets_in_secret_store(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    secrets = MemorySecretStore()
    repository = ConfigRepository(path, secrets)
    config = AppConfig(workspace=tmp_path / "workspace")
    config.stt.api_key = "stt-secret"
    config.llm.api_key = "llm-secret"

    repository.save(config)

    stored = path.read_text(encoding="utf-8")
    assert "stt-secret" not in stored
    assert "llm-secret" not in stored
    assert repository.masked_dict()["stt_api_key"] == "********"


def test_environment_overrides_saved_provider_config(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"stt_mode": "api", "stt_local_model": "base"}), encoding="utf-8")
    monkeypatch.setenv("STT_MODE", "local")
    monkeypatch.setenv("STT_LOCAL_MODEL", "small")

    config = ConfigRepository(path, MemorySecretStore()).load()

    assert config.stt.mode == "local"
    assert config.stt.local_model_name == "small"


def test_macos_keyring_is_skipped_when_temporary_home_has_no_login_keychain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lecture_auto.application.sys.platform", "darwin")
    monkeypatch.setattr("lecture_auto.application.Path.home", lambda: tmp_path)
    store = KeyringSecretStore()

    store.set("gemini_api_key", "temporary")

    assert store.get("gemini_api_key") == "temporary"
