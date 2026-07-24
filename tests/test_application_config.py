from __future__ import annotations

import json
from pathlib import Path

from lecture_auto.application import AppConfig, ConfigRepository, KeyringSecretStore
from lecture_auto.stt_config import STTConfig


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.reads: list[str] = []
        self.deletes: list[str] = []

    def get(self, name: str) -> str | None:
        self.reads.append(name)
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.deletes.append(name)
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


def test_local_stt_performance_options_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    repository = ConfigRepository(path, MemorySecretStore())
    expected = STTConfig(
        mode="local",
        local_model_name="base",
        language="ko",
        local_device="auto",
        compute_type="auto",
        batch_size=4,
        beam_size=1,
        temperature=0.0,
        vad_filter=True,
        vad_min_silence_duration_ms=1000,
        condition_on_previous_text=False,
        word_timestamps=True,
        hotwords="OpenGL rasterization",
        cpu_threads=8,
        num_workers=2,
    )

    repository.save(AppConfig(workspace=tmp_path / "workspace", stt=expected))
    loaded = repository.load(load_secrets=False)

    assert loaded.stt == expected


def test_app_load_does_not_access_keychain(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"stt_mode": "api", "llm_provider": "gemini"}),
        encoding="utf-8",
    )
    secrets = MemorySecretStore()
    secrets.values = {
        "stt_api_key": "stored-stt-key",
        "gemini_api_key": "stored-gemini-key",
    }

    config = ConfigRepository(path, secrets).load(load_secrets=False)

    assert config.stt.api_key is None
    assert config.llm.api_key is None
    assert secrets.reads == []


def test_saving_inactive_api_providers_preserves_keychain_items(tmp_path: Path) -> None:
    secrets = MemorySecretStore()
    secrets.values = {
        "stt_api_key": "stored-stt-key",
        "gemini_api_key": "stored-gemini-key",
    }
    repository = ConfigRepository(tmp_path / "config.json", secrets)
    config = AppConfig(workspace=tmp_path / "workspace")
    config.stt.mode = "local"
    config.llm.provider = "ollama"

    repository.save(config)

    assert secrets.values == {
        "stt_api_key": "stored-stt-key",
        "gemini_api_key": "stored-gemini-key",
    }
    assert secrets.deletes == []


def test_saving_active_providers_without_new_keys_preserves_keychain_items(tmp_path: Path) -> None:
    secrets = MemorySecretStore()
    secrets.values = {
        "stt_api_key": "stored-stt-key",
        "gemini_api_key": "stored-gemini-key",
    }
    repository = ConfigRepository(tmp_path / "config.json", secrets)
    config = AppConfig(workspace=tmp_path / "workspace")

    repository.save(config)

    assert secrets.values == {
        "stt_api_key": "stored-stt-key",
        "gemini_api_key": "stored-gemini-key",
    }
    assert secrets.reads == []
    assert secrets.deletes == []


def test_macos_keyring_is_skipped_when_temporary_home_has_no_login_keychain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lecture_auto.application.sys.platform", "darwin")
    monkeypatch.setattr("lecture_auto.application.Path.home", lambda: tmp_path)
    store = KeyringSecretStore()

    store.set("gemini_api_key", "temporary")

    assert store.get("gemini_api_key") == "temporary"
