from __future__ import annotations

import json
import time
from threading import Event
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QCloseEvent

from lecture_auto.application import AppConfig, ConfigRepository
from lecture_auto.capture_runtime import AudioDevice
from lecture_auto.gui.app import MainWindow
from lecture_auto.local_runtime import RuntimeStatus


class MemorySecrets:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.reads: list[str] = []

    def get(self, name: str) -> str | None:
        self.reads.append(name)
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


def make_window(tmp_path: Path, qtbot) -> MainWindow:
    repository = ConfigRepository(tmp_path / "config.json", MemorySecrets())
    config = AppConfig(workspace=tmp_path / "workspace")
    repository.save(config)
    window = MainWindow(repository, config)
    window.container.runtime.allow_development_python = False
    qtbot.addWidget(window)
    return window


def test_main_window_navigates_and_shows_created_session(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.container.session.session_create("week-01", "2026-07-12", "Intro", "CS101")

    window.refresh_all()
    window.sessions_page.select_session("week-01")
    window.show_page(1)

    assert window.stack.currentWidget() is window.sessions_page
    assert window.sessions_page.current_session_id == "week-01"
    assert window.sessions_page.detail_title.text() == "Intro"


def test_settings_lists_matching_capture_devices(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.container.session.runtime_adapter.list_devices = lambda: [
        AudioDevice("mic", "Built-in microphone", "microphone", "avfoundation"),
        AudioDevice("loop", "BlackHole", "system_audio", "avfoundation"),
    ]

    window.show_page(3)

    assert window.settings_page.devices.count() == 1
    assert window.settings_page.devices.currentText() == "Built-in microphone"


def test_workspace_picker_applies_immediately_and_persists(tmp_path: Path, qtbot, monkeypatch) -> None:
    window = make_window(tmp_path, qtbot)
    selected = tmp_path / "semester-3-1"
    selected.mkdir()
    monkeypatch.setattr(
        "lecture_auto.gui.app.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: str(selected),
    )

    window.show_page(3)
    window.settings_page.choose_workspace()
    window.show_page(0)
    window.show_page(3)

    assert window.config.workspace == selected.resolve()
    assert window.repository.load().workspace == selected.resolve()
    assert json.loads(window.repository.path.read_text(encoding="utf-8"))["workspace"] == str(selected.resolve())
    assert window.container.session.store.metadata_file == selected / "metadata" / "sessions.json"
    assert window.settings_page.workspace.text() == str(selected.resolve())
    for directory in ("metadata", "recordings", "transcripts", "notes", "materials"):
        assert (selected / directory).is_dir()


def test_background_job_completes_without_blocking_ui(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)

    window.run_background("test", None, lambda _token, _progress, _job: "done")

    qtbot.waitUntil(lambda: window.jobs.active_count == 0, timeout=3000)
    assert "완료" in window.task_list.item(0).text()


def test_non_blocking_status_job_does_not_show_exit_confirmation(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    started = Event()

    def status_probe(token, _progress, _job):
        started.set()
        while not token.is_cancelled:
            time.sleep(0.01)

    window.run_background(
        "status probe",
        None,
        status_probe,
        block_close=False,
    )
    qtbot.waitUntil(started.is_set, timeout=3000)

    event = QCloseEvent()
    with patch("lecture_auto.gui.app.QMessageBox.question") as question:
        window.closeEvent(event)

    assert event.isAccepted()
    question.assert_not_called()
    qtbot.waitUntil(lambda: window.jobs.active_count == 0, timeout=3000)


def test_api_key_is_loaded_only_when_api_action_is_requested(tmp_path: Path, qtbot) -> None:
    secrets = MemorySecrets()
    secrets.values["stt_api_key"] = "stored-stt-key"
    repository = ConfigRepository(tmp_path / "config.json", secrets)
    config = AppConfig(workspace=tmp_path / "workspace")
    config.llm.provider = "ollama"
    repository.save(config)

    window = MainWindow(repository, config)
    qtbot.addWidget(window)

    assert secrets.reads == []
    assert window.ensure_provider_credentials("stt") is True
    assert secrets.reads == ["stt_api_key"]
    assert window.config.stt.api_key == "stored-stt-key"


def test_local_ai_section_shows_uninstalled_features(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)

    window.settings_page.set_runtime_status(RuntimeStatus(error="not installed"))

    assert window.settings_page.runtime_whisper_status.text() == "설치되지 않음"
    assert window.settings_page.runtime_deepfilter_status.text() == "설치되지 않음"
    assert window.settings_page.runtime_gemini_status.text() == "설치되지 않음"
    labels = {button.text() for button in window.settings_page.findChildren(type(window.nav_buttons[0]))}
    assert {
        "Whisper 설치",
        "DeepFilterNet 설치",
        "Gemini 애드온 설치",
        "전체 애드온 설치",
        "설치 복구",
        "runtime 제거",
    } <= labels
