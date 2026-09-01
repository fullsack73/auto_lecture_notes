from __future__ import annotations

import json
import time
from threading import Event
from pathlib import Path
from unittest.mock import call, patch

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QFrame,
    QLabel,
    QPushButton,
    QStatusBar,
)

from lecture_auto.application import AppConfig, ConfigRepository
from lecture_auto.capture_runtime import AudioDevice, NoopCaptureRuntimeAdapter
from lecture_auto.gui.app import APP_STYLE, MainWindow
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


def test_table_style_avoids_macos_header_corner_artifact() -> None:
    assert "QHeaderView::section:first" not in APP_STYLE


def test_main_window_navigates_and_shows_created_session(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.container.session.session_create("week-01", "2026-07-12", "Intro", "CS101")

    window.refresh_all()
    window.sessions_page.select_session("week-01")
    window.show_page(1)

    assert window.stack.currentWidget() is window.sessions_page
    assert window.sessions_page.current_session_id == "week-01"
    assert window.sessions_page.detail_title.text() == "Intro"


def test_session_transcript_preview_prefers_refined_version(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.container.session.session_create("week-01", "2026-07-12", "Intro", "CS101")
    session = window.container.session.store.get_by_session_id("week-01")
    assert session is not None
    session["transcript_file_path"] = "transcripts/CS101/week-01-raw.md"
    window.container.session.store.upsert(session)

    transcripts = window.config.workspace / "transcripts" / "CS101"
    transcripts.mkdir(parents=True)
    (transcripts / "week-01-raw.md").write_text("raw version", encoding="utf-8")
    (transcripts / "week-01-edited.md").write_text("refined version", encoding="utf-8")

    window.sessions_page.select_session("week-01")

    assert window.sessions_page.transcript_view.toPlainText() == "refined version"


def test_command_feedback_does_not_create_bottom_status_bar(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)

    result = window.execute(
        lambda: window.container.session.session_create("week-01", "2026-07-12", "Intro", "CS101"),
        refresh=False,
    )

    assert result is not None
    assert window.findChildren(QStatusBar) == []
    assert window.task_status.text() == result.message


def test_session_actions_follow_recording_to_notes_workflow(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)

    stage_titles = [
        label.text()
        for label in window.sessions_page.findChildren(QLabel)
        if label.objectName() == "WorkflowTitle"
    ]
    buttons = {
        button.text().replace("  →", ""): button
        for button in window.sessions_page.action_buttons
    }

    assert stage_titles == ["녹음·오디오", "전사", "복습 노트"]
    assert {
        "정보 수정",
        "세션 삭제",
        "녹음 시작",
        "녹음 중지",
        "오디오 파일 가져오기",
        "볼륨 보정",
        "노이즈 제거",
        "전사 시작",
        "전사문 다듬기",
        "강의 자료 첨부",
        "노트 미리보기",
        "노트 저장",
        "녹음 폴더 열기",
        "전사문 폴더 열기",
        "노트 폴더 열기",
    } == set(buttons)
    assert buttons["녹음 시작"].objectName() == "WorkflowPrimary"
    assert buttons["전사 시작"].objectName() == "WorkflowAccent"
    assert buttons["노트 저장"].objectName() == "WorkflowAccent"
    assert all(
        buttons[label].objectName() == "FolderLink"
        for label in ("녹음 폴더 열기", "전사문 폴더 열기", "노트 폴더 열기")
    )
    assert all(not button.isEnabled() for button in buttons.values())


def test_recording_session_shows_live_microphone_level(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.container.session.runtime_adapter = NoopCaptureRuntimeAdapter()
    window.container.session.session_create("week-01", "2026-07-12", "Intro", "CS101")
    window.container.session.capture_start("week-01")
    window.container.session.runtime_adapter.capture_level = lambda _session_id: -18.5

    window.sessions_page.select_session("week-01")
    window.sessions_page._refresh_capture_level()

    try:
        assert not window.sessions_page.capture_meter_row.isHidden()
        assert window.sessions_page.capture_meter.value() == 42
        assert window.sessions_page.capture_level_label.text() == "-18.5 dBFS"
    finally:
        window.container.session.capture_stop("week-01")


def test_main_window_starts_with_capture_runtime_metadata(tmp_path: Path, qtbot) -> None:
    workspace = tmp_path / "workspace"
    metadata_file = workspace / "metadata" / "sessions.json"
    metadata_file.parent.mkdir(parents=True)
    metadata_file.write_text(
        json.dumps(
            [
                {
                    "session_id": "captured",
                    "date": "2026-07-12",
                    "title": "Captured lecture",
                    "course": "CS101",
                    "status": "completed",
                    "audio_file_path": "recordings/captured.wav",
                    "timestamps": {
                        "created_at": "2026-07-12T10:00:00+00:00",
                        "capture_process_id": 31079,
                        "capture_backend": "ffmpeg",
                        "recording_completed_at": "2026-07-12T11:00:00+00:00",
                    },
                    "naming_pending": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    repository = ConfigRepository(tmp_path / "config.json", MemorySecrets())
    config = AppConfig(workspace=workspace)
    repository.save(config)

    window = MainWindow(repository, config)
    qtbot.addWidget(window)

    assert window.library_page.table.rowCount() == 1
    assert window.library_page.table.item(0, 0).text() == "captured"


def test_library_folder_buttons_open_default_selected_session(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.container.session.session_create(
        "week-01",
        "2026-07-12",
        "Intro",
        "CS101",
    )
    window.library_page.refresh()

    assert window.library_page.table.currentRow() == 0
    assert all(button.isEnabled() for button in window.library_page.open_buttons)

    with patch.object(window.container.library, "library_open") as open_mock:
        for button in window.library_page.open_buttons:
            button.click()

    assert open_mock.call_args_list == [
        call("week-01", open_transcript=False, open_recordings=False),
        call("week-01", open_transcript=True, open_recordings=False),
        call("week-01", open_transcript=False, open_recordings=True),
    ]


def test_library_folder_buttons_disable_without_sessions(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)

    window.library_page.refresh()

    assert all(not button.isEnabled() for button in window.library_page.open_buttons)
    assert window.library_page.open_folder_row.spacing() == 12
    assert all(
        button.objectName() == "LibraryFolderButton"
        for button in window.library_page.open_buttons
    )


def test_session_table_headers_sort_and_preserve_selection(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    sessions = (
        ("session-z", "2026-07-12", "Zebra", "Biology"),
        ("session-a", "2026-07-10", "alpha", "Chemistry"),
        ("session-b", "2026-07-11", "Beta", "Art"),
    )
    for session_id, session_date, title, course in sessions:
        window.container.session.session_create(session_id, session_date, title, course)

    window.show_page(2)
    window.show()
    qtbot.wait(20)
    table = window.library_page.table
    header = table.horizontalHeader()

    def values(column: int) -> list[str]:
        return [table.item(row, column).text() for row in range(table.rowCount())]

    def click_header(column: int) -> None:
        position = QPoint(
            header.sectionPosition(column) + header.sectionSize(column) // 2,
            header.height() // 2,
        )
        QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, position)
        qtbot.wait(10)

    click_header(2)
    assert values(2) == ["alpha", "Beta", "Zebra"]
    click_header(2)
    assert values(2) == ["Zebra", "Beta", "alpha"]

    click_header(3)
    assert values(3) == ["Art", "Biology", "Chemistry"]
    chemistry_row = values(0).index("session-a")
    table.selectRow(chemistry_row)

    window.library_page.refresh()

    assert values(3) == ["Art", "Biology", "Chemistry"]
    assert table.item(table.currentRow(), 0).text() == "session-a"


def test_settings_lists_matching_capture_devices(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    window.container.session.runtime_adapter.list_devices = lambda: [
        AudioDevice("mic", "Built-in microphone", "microphone", "avfoundation"),
        AudioDevice("loop", "BlackHole", "system_audio", "avfoundation"),
    ]

    window.show_page(3)

    assert window.settings_page.devices.count() == 1
    assert window.settings_page.devices.currentText() == "Built-in microphone"


def test_settings_groups_runtime_and_model_actions(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    page = window.settings_page
    panels = [
        panel
        for panel in page.findChildren(QFrame)
        if panel.objectName() == "SettingsActionPanel"
    ]
    button_labels = {button.text() for button in page.findChildren(QPushButton)}

    assert len(panels) == 2
    assert page.runtime_feature.count() == 4
    assert {
        "선택 항목 설치",
        "상태 다시 확인",
        "설치 복구",
        "외부 Python",
        "Runtime 제거",
        "모델 받기",
        "모델 삭제",
        "연결 확인",
    } <= button_labels
    assert {
        "Whisper 설치",
        "DeepFilterNet 설치",
        "Gemini 애드온 설치",
        "전체 애드온 설치",
    }.isdisjoint(button_labels)
    styled_actions = {
        button.text(): button.objectName()
        for button in page.findChildren(QPushButton)
        if button.text() in {"설치 복구", "외부 Python", "Runtime 제거", "모델 삭제"}
    }
    assert styled_actions == {
        "설치 복구": "SettingsLink",
        "외부 Python": "SettingsLink",
        "Runtime 제거": "SettingsDangerLink",
        "모델 삭제": "SettingsDangerLink",
    }

    with patch.object(page, "_install_runtime") as install_runtime:
        page.runtime_feature.setCurrentIndex(page.runtime_feature.findData("deepfilter"))
        page.install_selected_runtime()

    install_runtime.assert_called_once_with("deepfilter")


def test_settings_disable_fields_for_inactive_stt_and_llm_providers(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    page = window.settings_page
    page._runtime_probe_requested = True
    page.stt_key.setText("keep-stt-key")
    page.llm_key.setText("keep-llm-key")

    page.stt_mode.setCurrentIndex(page.stt_mode.findData("local"))

    assert all(not control.isEnabled() for control in page._stt_api_controls)
    assert all(control.isEnabled() for control in page._stt_local_controls)
    assert page.stt_key.text() == "keep-stt-key"

    page.stt_mode.setCurrentIndex(page.stt_mode.findData("api"))

    assert all(control.isEnabled() for control in page._stt_api_controls)
    assert all(not control.isEnabled() for control in page._stt_local_controls)

    page.llm_provider.setCurrentIndex(page.llm_provider.findData("ollama"))

    assert all(not control.isEnabled() for control in page._gemini_controls)
    assert all(control.isEnabled() for control in page._ollama_controls)
    assert page.llm_key.text() == "keep-llm-key"

    page.llm_provider.setCurrentIndex(page.llm_provider.findData("gemini"))

    assert all(control.isEnabled() for control in page._gemini_controls)
    assert all(not control.isEnabled() for control in page._ollama_controls)


def test_settings_value_controls_ignore_mouse_wheel(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    page = window.settings_page
    page.stt_model.setCurrentIndex(1)
    page.dynaudnorm_f.setValue(150)
    page.gain_db.setValue(3.0)

    for widget in (page.stt_model, page.dynaudnorm_f, page.gain_db):
        widget.setFocus()
        event = QWheelEvent(
            QPointF(5, 5),
            QPointF(5, 5),
            QPoint(),
            QPoint(0, -120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(widget, event)

    assert page.stt_model.currentIndex() == 1
    assert page.dynaudnorm_f.value() == 150
    assert page.gain_db.value() == 3.0


def test_settings_controls_use_polished_popup_spin_and_device_layout(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    page = window.settings_page

    assert page.language.view().objectName() == "ComboPopup"
    assert page.dynaudnorm_f.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert page.gain_db.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert page.device_row.stretch(0) == 1
    assert page.device_refresh.objectName() == "DeviceRefresh"
    assert page.device_refresh.maximumWidth() == 108
    assert "QComboBoxPrivateContainer" in APP_STYLE


def test_settings_changes_apply_automatically(tmp_path: Path, qtbot) -> None:
    window = make_window(tmp_path, qtbot)
    page = window.settings_page
    page._runtime_probe_requested = True
    window.show_page(3)

    page.audio_format.setCurrentIndex(page.audio_format.findData("mp3"))
    qtbot.waitUntil(lambda: window.config.audio_format == "mp3", timeout=2000)

    page.stt_language.setText("en")
    page.stt_language.editingFinished.emit()
    qtbot.waitUntil(lambda: window.config.stt.language == "en", timeout=2000)

    persisted = window.repository.load(load_secrets=False)
    assert persisted.audio_format == "mp3"
    assert persisted.stt.language == "en"
    assert page.auto_save_status.text() == "저장됨"
    assert "설정 저장" not in {
        button.text() for button in page.findChildren(QPushButton)
    }


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
    labels = {button.text() for button in window.settings_page.findChildren(QPushButton)}
    assert {
        "선택 항목 설치",
        "상태 다시 확인",
        "설치 복구",
        "Runtime 제거",
    } <= labels
    assert [
        window.settings_page.runtime_feature.itemData(index)
        for index in range(window.settings_page.runtime_feature.count())
    ] == ["whisper", "deepfilter", "gemini", "all"]
