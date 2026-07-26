from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QDate, Qt, QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from lecture_auto.application import (
    AppConfig,
    ConfigRepository,
    ServiceContainer,
    build_service_container,
    ensure_workspace_structure,
)
from lecture_auto.capture_runtime import AudioDevice
from lecture_auto.gui.i18n import Translator
from lecture_auto.gui.jobs import JobController
from lecture_auto.llm_config import LLMConfig
from lecture_auto.local_runtime import RuntimeStatus
from lecture_auto.session_service import CommandResult, SessionCommandError
from lecture_auto.stt_config import (
    LOCAL_MODEL_RECOMMENDATIONS,
    LOCAL_STT_HARDWARE_GUIDE,
    STTConfig,
)
from lecture_auto.tasking import TaskCancelledError, TaskEvent


APP_STYLE = """
* {
    font-family: "Pretendard Variable", "Apple SD Gothic Neo";
    font-size: 13px;
    color: #18231e;
}
QMainWindow, QDialog, QWidget#AppRoot { background: #f3f5f2; }
QWidget#Page, QStackedWidget { background: transparent; }
QFrame#Sidebar { background: #17241e; border: 0; }
QLabel#BrandMark {
    color: #f7faf8;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.4px;
    padding: 2px 4px;
}
QLabel#BrandCaption {
    color: #8fa198;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.2px;
    padding: 0 4px;
}
QFrame#Sidebar QPushButton {
    color: #bcc8c1;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
    min-height: 24px;
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 7px;
    padding: 10px 14px;
    margin: 2px 0;
    background: transparent;
}
QFrame#Sidebar QPushButton:hover { color: #ffffff; background: #21322a; }
QFrame#Sidebar QPushButton:checked {
    color: #ffffff;
    background: #294338;
    border-left-color: #89c9a8;
}
QFrame#Sidebar QLabel#SidebarMeta {
    color: #82938a;
    font-size: 11px;
    padding: 4px;
}
QPushButton {
    min-height: 20px;
    padding: 8px 14px;
    color: #24332b;
    font-weight: 600;
    border: 1px solid #cbd4ce;
    border-radius: 7px;
    background: #ffffff;
}
QPushButton:hover { background: #f6f9f7; border-color: #9eafa5; }
QPushButton:pressed { background: #edf2ef; padding-top: 9px; padding-bottom: 7px; }
QPushButton:focus { border: 2px solid #34765a; padding: 7px 13px; }
QPushButton:disabled { color: #9ba7a0; background: #edf0ee; border-color: #dde3df; }
QPushButton#Primary {
    background: #236b50;
    color: #ffffff;
    border-color: #236b50;
    padding-left: 18px;
    padding-right: 18px;
}
QPushButton#Primary:hover { background: #1b5b43; border-color: #1b5b43; }
QPushButton#Primary:pressed { background: #164b37; }
QPushButton#Danger { color: #9c403b; border-color: #e0c4c1; background: #fffafa; }
QPushButton#Danger:hover { background: #fbecea; border-color: #cd928d; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    min-height: 22px;
    padding: 7px 9px;
    color: #17231d;
    background: #ffffff;
    border: 1px solid #cad3cd;
    border-radius: 6px;
    selection-background-color: #34765a;
    selection-color: #ffffff;
}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QSpinBox:hover,
QDoubleSpinBox:hover, QPlainTextEdit:hover { border-color: #9eafa5; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QPlainTextEdit:focus { border: 2px solid #34765a; padding: 6px 8px; }
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QPlainTextEdit:disabled {
    color: #98a49d;
    background: #edf0ee;
    border-color: #dde3df;
}
QLabel:disabled { color: #9ba7a0; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox QAbstractItemView {
    color: #18231e;
    background: #ffffff;
    border: 1px solid #b9c6be;
    selection-background-color: #dceae2;
    selection-color: #143326;
}
QTableWidget, QListWidget, QTextBrowser {
    color: #1d2a23;
    background: #ffffff;
    alternate-background-color: #f8faf8;
    border: 1px solid #d4dcd7;
    border-radius: 9px;
    outline: 0;
    selection-background-color: #dcebe2;
    selection-color: #153b2a;
}
QTableWidget { gridline-color: #e8edea; }
QTableWidget::item { padding: 8px 10px; border-bottom: 1px solid #edf1ee; }
QTableWidget::item:selected { background: #dcebe2; color: #153b2a; }
QListWidget::item { min-height: 38px; padding: 9px 11px; border-bottom: 1px solid #edf1ee; }
QListWidget::item:hover { background: #f3f7f4; }
QListWidget::item:selected { background: #dcebe2; color: #153b2a; border-left: 3px solid #34765a; }
QHeaderView::section {
    color: #536259;
    background: #eef2ef;
    font-size: 11px;
    font-weight: 700;
    padding: 10px;
    border: 0;
    border-bottom: 1px solid #d8dfda;
}
/* Rounded header sections expose the Cocoa viewport as a black corner. */
QTableCornerButton::section { background: #eef2ef; border: 0; }
QTabWidget::pane { background: #ffffff; border: 1px solid #d4dcd7; border-radius: 8px; top: -1px; }
QTabBar::tab {
    color: #68756e;
    background: transparent;
    font-weight: 600;
    padding: 9px 16px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: #26372e; }
QTabBar::tab:selected { color: #1d5f46; border-bottom-color: #34765a; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #c2ccc6; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #9fada5; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar {
    min-height: 7px;
    max-height: 7px;
    color: transparent;
    background: #dfe6e1;
    border: 0;
    border-radius: 3px;
}
QProgressBar::chunk { background: #34765a; border-radius: 3px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #aebbb3; border-radius: 4px; background: #ffffff; }
QCheckBox::indicator:checked { background: #34765a; border-color: #34765a; }
QLabel#PageEyebrow {
    color: #34765a;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.1px;
}
QLabel#PageTitle { color: #14201a; font-size: 30px; font-weight: 800; letter-spacing: -0.7px; }
QLabel#DetailTitle { color: #16231c; font-size: 22px; font-weight: 750; letter-spacing: -0.3px; }
QLabel#SectionTitle { color: #1b2921; font-size: 16px; font-weight: 700; }
QLabel#Muted { color: #66736c; font-size: 13px; }
QLabel#Summary { color: #526158; font-size: 12px; font-weight: 600; }
QLabel#StatusReady { color: #2c684e; font-size: 12px; font-weight: 700; }
QFrame#EmptyState {
    background: #e9efeb;
    border: 1px solid #d5dfd9;
    border-radius: 12px;
}
QLabel#EmptyGlyph { color: #34765a; font-size: 26px; font-weight: 800; }
QLabel#EmptyTitle { color: #18251e; font-size: 18px; font-weight: 750; }
QLabel#EmptyBody { color: #67756d; font-size: 13px; }
QFrame#DetailPanel, QWidget#SettingsPanel {
    background: #f9fbf9;
    border: 1px solid #dbe2dd;
    border-radius: 11px;
}
QFrame#ActionPanel {
    background: #eef3ef;
    border: 1px solid #d7e1db;
    border-radius: 12px;
}
QFrame#WorkflowStage { background: transparent; border: 0; }
QFrame#WorkflowDivider { background: #d2ddd6; border: 0; min-width: 1px; max-width: 1px; }
QLabel#WorkflowStep {
    color: #34765a;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#WorkflowTitle { color: #17251e; font-size: 16px; font-weight: 750; }
QLabel#WorkflowHint { color: #6c7971; font-size: 11px; }
QPushButton#CompactAction, QPushButton#DangerCompact {
    min-height: 18px;
    padding: 6px 10px;
    font-size: 12px;
    border-radius: 6px;
}
QPushButton#DangerCompact { color: #9c403b; border-color: #dfc2bf; background: #fffafa; }
QPushButton#DangerCompact:hover { background: #fbecea; border-color: #cd928d; }
QPushButton#WorkflowAction, QPushButton#WorkflowAccent, QPushButton#WorkflowPrimary {
    min-height: 22px;
    padding: 8px 11px;
    text-align: left;
    border-radius: 7px;
}
QPushButton#WorkflowAccent {
    color: #215d45;
    background: #e3eee7;
    border-color: #b9d0c2;
}
QPushButton#WorkflowAccent:hover { background: #d8e8de; border-color: #95b8a3; }
QPushButton#WorkflowPrimary {
    color: #ffffff;
    background: #236b50;
    border-color: #236b50;
}
QPushButton#WorkflowPrimary:hover { background: #1b5b43; border-color: #1b5b43; }
QPushButton#FolderLink {
    min-height: 18px;
    padding: 6px 4px;
    color: #35634f;
    background: transparent;
    border: 0;
    text-align: left;
    font-size: 11px;
}
QPushButton#FolderLink:hover { color: #174c36; background: #e1eae4; }
QPushButton#CompactAction:disabled,
QPushButton#DangerCompact:disabled,
QPushButton#WorkflowAction:disabled,
QPushButton#WorkflowAccent:disabled,
QPushButton#WorkflowPrimary:disabled {
    color: #9ba7a0;
    background: #edf0ee;
    border-color: #dde3df;
}
QPushButton#FolderLink:disabled {
    color: #9ba7a0;
    background: transparent;
}
QFrame#TaskTray {
    background: #e9efeb;
    border: 1px solid #d4ddd7;
    border-radius: 9px;
}
QFrame#SettingsActionPanel {
    background: #eef3ef;
    border: 1px solid #d7e1db;
    border-radius: 11px;
}
QFrame#SettingsActionPanel QFrame#SettingsDivider {
    background: #d2ddd6;
    border: 0;
    min-width: 1px;
    max-width: 1px;
}
QLabel#SettingsActionTitle { color: #17251e; font-size: 15px; font-weight: 750; }
QLabel#SettingsActionBody { color: #66746c; font-size: 11px; }
QLabel#SettingsFieldLabel { color: #6a7870; font-size: 10px; font-weight: 700; }
QLabel#SettingsPath { color: #506158; font-size: 10px; }
QPushButton#SettingsAccent {
    color: #215d45;
    background: #dfece4;
    border-color: #b4cdbd;
}
QPushButton#SettingsAccent:hover { background: #d3e5da; border-color: #91b49e; }
QPushButton#SettingsLink, QPushButton#SettingsDangerLink {
    min-height: 20px;
    padding: 6px 9px;
    background: #f8faf8;
    border: 1px solid #cbd7d0;
    border-radius: 6px;
    text-align: center;
    font-size: 11px;
}
QPushButton#SettingsLink { color: #35634f; }
QPushButton#SettingsLink:hover {
    color: #174c36;
    background: #e5eee8;
    border-color: #a9bfb2;
}
QPushButton#SettingsDangerLink {
    color: #9c403b;
    background: #fffafa;
    border-color: #dfc2bf;
}
QPushButton#SettingsDangerLink:hover {
    background: #f8e9e7;
    border-color: #cd928d;
}
QFrame#TaskTray QListWidget { background: #f8faf8; border-color: #d7dfda; }
QToolTip { color: #ffffff; background: #17241e; border: 1px solid #3d5147; padding: 5px; }
"""


class SessionDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, session: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("세션")
        layout = QFormLayout(self)
        self.session_id = QLineEdit(str((session or {}).get("session_id") or ""))
        self.session_id.setReadOnly(session is not None)
        self.session_date = QDateEdit(calendarPopup=True)
        self.session_date.setDisplayFormat("yyyy-MM-dd")
        raw_date = str((session or {}).get("date") or date.today().isoformat())
        self.session_date.setDate(QDate.fromString(raw_date, "yyyy-MM-dd"))
        self.title = QLineEdit(str((session or {}).get("title") or ""))
        self.course = QLineEdit(str((session or {}).get("course") or ""))
        layout.addRow("ID", self.session_id)
        layout.addRow("날짜", self.session_date)
        layout.addRow("제목", self.title)
        layout.addRow("과목", self.course)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict[str, str | None]:
        return {
            "session_id": self.session_id.text().strip(),
            "date": self.session_date.date().toString("yyyy-MM-dd"),
            "title": self.title.text().strip() or None,
            "course": self.course.text().strip() or None,
        }


class OnboardingDialog(QDialog):
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lecture Auto 시작 설정")
        self.setMinimumWidth(520)
        layout = QFormLayout(self)
        intro = QLabel("저장 위치와 기본 처리 방식을 선택하세요. 이후 설정에서 변경할 수 있습니다.")
        intro.setWordWrap(True)
        layout.addRow(intro)
        self.workspace = QLineEdit(str(config.workspace))
        choose = QPushButton("찾기")
        choose.clicked.connect(self._choose_workspace)
        row = QHBoxLayout()
        row.addWidget(self.workspace)
        row.addWidget(choose)
        layout.addRow("Workspace", row)
        self.language = QComboBox()
        self.language.addItem("한국어", "ko")
        self.language.addItem("English", "en")
        layout.addRow("UI 언어", self.language)
        self.stt_mode = QComboBox()
        self.stt_mode.addItem("로컬 Whisper", "local")
        self.stt_mode.addItem("API", "api")
        layout.addRow("STT", self.stt_mode)
        self.llm_provider = QComboBox()
        self.llm_provider.addItem("Google Gemini API", "gemini")
        self.llm_provider.addItem("로컬 Ollama", "ollama")
        layout.addRow("LLM", self.llm_provider)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _choose_workspace(self) -> None:
        value = QFileDialog.getExistingDirectory(self, "Workspace 선택", self.workspace.text())
        if value:
            self.workspace.setText(value)

    def apply(self, config: AppConfig) -> AppConfig:
        config.workspace = Path(self.workspace.text()).expanduser().resolve()
        config.ui_language = str(self.language.currentData())
        config.stt.mode = self.stt_mode.currentData()
        config.llm.provider = str(self.llm_provider.currentData())
        if config.llm.provider == "ollama" and config.llm.model_name.startswith("gemini"):
            config.llm.model_name = "gemma4:31b-cloud"
        return config


class EmptyState(QFrame):
    def __init__(
        self,
        title: str,
        body: str,
        action_label: str | None = None,
        action: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("EmptyState")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 32, 28, 36)
        layout.setSpacing(7)
        layout.addStretch()
        glyph = QLabel("＋")
        glyph.setObjectName("EmptyGlyph")
        glyph.setAlignment(Qt.AlignCenter)
        layout.addWidget(glyph)
        heading = QLabel(title)
        heading.setObjectName("EmptyTitle")
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)
        description = QLabel(body)
        description.setObjectName("EmptyBody")
        description.setAlignment(Qt.AlignCenter)
        description.setWordWrap(True)
        layout.addWidget(description)
        if action_label and action:
            button_row = QHBoxLayout()
            button_row.addStretch()
            button = QPushButton(action_label)
            button.setObjectName("Primary")
            button.clicked.connect(action)
            button_row.addWidget(button)
            button_row.addStretch()
            layout.addSpacing(8)
            layout.addLayout(button_row)
        layout.addStretch()


class HomePage(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.setObjectName("Page")
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        eyebrow = QLabel("LECTURE WORKSPACE")
        eyebrow.setObjectName("PageEyebrow")
        layout.addWidget(eyebrow)
        layout.addSpacing(7)
        header = QHBoxLayout()
        header.setSpacing(20)
        copy = QVBoxLayout()
        copy.setSpacing(6)
        title = QLabel("강의를 기록하고, 바로 정리하세요")
        title.setObjectName("PageTitle")
        copy.addWidget(title)
        subtitle = QLabel("녹음부터 전사와 구조화 노트까지 한 흐름으로 처리합니다.")
        subtitle.setObjectName("Muted")
        copy.addWidget(subtitle)
        header.addLayout(copy)
        header.addStretch()
        create = QPushButton("새 세션")
        create.setObjectName("Primary")
        create.clicked.connect(window.create_session)
        header.addWidget(create, 0, Qt.AlignVCenter)
        layout.addLayout(header)
        layout.addSpacing(30)
        section_header = QHBoxLayout()
        section_title = QLabel("최근 세션")
        section_title.setObjectName("SectionTitle")
        section_header.addWidget(section_title)
        section_header.addStretch()
        self.summary = QLabel()
        self.summary.setObjectName("Summary")
        section_header.addWidget(self.summary)
        layout.addLayout(section_header)
        layout.addSpacing(10)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "날짜", "제목", "과목", "상태"])
        configure_session_table(self.table)
        self.table.doubleClicked.connect(self._open_selected)
        layout.addWidget(self.table)
        self.empty_state = EmptyState(
            "아직 세션이 없습니다",
            "첫 강의 세션을 만들면 녹음, 전사, 노트 생성 과정을 여기서 확인할 수 있습니다.",
            "첫 세션 만들기",
            window.create_session,
        )
        layout.addWidget(self.empty_state, 1)

    def refresh(self) -> None:
        sessions = self.window.container.session.session_history().payload["sessions"]
        self.summary.setText(f"전체 {len(sessions)}개  ·  실행 중 {self.window.jobs.active_count}개")
        fill_session_table(self.table, sessions[:10])
        has_sessions = bool(sessions)
        self.table.setVisible(has_sessions)
        self.empty_state.setVisible(not has_sessions)

    def _open_selected(self) -> None:
        item = self.table.item(self.table.currentRow(), 0)
        if item:
            self.window.sessions_page.select_session(item.text())
            self.window.show_page(1)


class SessionsPage(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.setObjectName("Page")
        self.window = window
        self.current_session_id: str | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        eyebrow = QLabel("SESSION MANAGER")
        eyebrow.setObjectName("PageEyebrow")
        outer.addWidget(eyebrow)
        outer.addSpacing(7)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(5)
        title = QLabel("세션 관리")
        title.setObjectName("PageTitle")
        heading.addWidget(title)
        subtitle = QLabel("강의별 녹음과 전사, 노트 생성 상태를 한곳에서 관리합니다.")
        subtitle.setObjectName("Muted")
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        create = QPushButton("새 세션")
        create.setObjectName("Primary")
        create.clicked.connect(window.create_session)
        header.addWidget(create, 0, Qt.AlignVCenter)
        outer.addLayout(header)
        outer.addSpacing(24)
        self.search = QLineEdit()
        self.search.setPlaceholderText("ID, 제목 또는 과목으로 검색")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        outer.addWidget(self.search)
        outer.addSpacing(12)
        content = QHBoxLayout()
        content.setSpacing(14)
        self.list = QListWidget()
        self.list.setObjectName("SessionList")
        self.list.setMinimumWidth(280)
        self.list.setAlternatingRowColors(True)
        self.list.currentItemChanged.connect(self._selection_changed)
        content.addWidget(self.list, 1)
        detail = QFrame()
        detail.setObjectName("DetailPanel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(20, 18, 20, 20)
        detail_layout.setSpacing(12)
        self.action_buttons: list[QPushButton] = []

        def action_button(
            label: str,
            callback: Callable[[], None],
            object_name: str = "WorkflowAction",
        ) -> QPushButton:
            button = QPushButton(label)
            button.setObjectName(object_name)
            button.clicked.connect(callback)
            self.action_buttons.append(button)
            return button

        def workflow_stage(
            step: str,
            title: str,
            hint: str,
        ) -> tuple[QFrame, QVBoxLayout]:
            stage = QFrame()
            stage.setObjectName("WorkflowStage")
            stage_layout = QVBoxLayout(stage)
            stage_layout.setContentsMargins(0, 0, 0, 0)
            stage_layout.setSpacing(7)
            step_label = QLabel(step)
            step_label.setObjectName("WorkflowStep")
            stage_title = QLabel(title)
            stage_title.setObjectName("WorkflowTitle")
            stage_hint = QLabel(hint)
            stage_hint.setObjectName("WorkflowHint")
            stage_hint.setWordWrap(True)
            stage_layout.addWidget(step_label)
            stage_layout.addWidget(stage_title)
            stage_layout.addWidget(stage_hint)
            stage_layout.addSpacing(4)
            return stage, stage_layout

        detail_header = QHBoxLayout()
        detail_header.setSpacing(12)
        detail_copy = QVBoxLayout()
        detail_copy.setSpacing(4)
        self.detail_title = QLabel("세션을 선택하세요")
        self.detail_title.setObjectName("DetailTitle")
        self.detail_meta = QLabel()
        self.detail_meta.setObjectName("Muted")
        self.detail_meta.setWordWrap(True)
        detail_copy.addWidget(self.detail_title)
        detail_copy.addWidget(self.detail_meta)
        detail_header.addLayout(detail_copy, 1)
        detail_header.addWidget(
            action_button("정보 수정", self.edit_session, "CompactAction"),
            0,
            Qt.AlignTop,
        )
        detail_header.addWidget(
            action_button("세션 삭제", self.delete_session, "DangerCompact"),
            0,
            Qt.AlignTop,
        )
        detail_layout.addLayout(detail_header)

        action_panel = QFrame()
        action_panel.setObjectName("ActionPanel")
        workflow = QHBoxLayout(action_panel)
        workflow.setContentsMargins(18, 16, 18, 17)
        workflow.setSpacing(16)

        audio_stage, audio_layout = workflow_stage(
            "STEP 01",
            "녹음·오디오",
            "새로 녹음하거나 기존 음성을 가져와 먼저 정리합니다.",
        )
        capture_row = QHBoxLayout()
        capture_row.setSpacing(7)
        capture_row.addWidget(action_button("녹음 시작", self.capture_start, "WorkflowPrimary"))
        capture_row.addWidget(action_button("녹음 중지", self.capture_stop))
        audio_layout.addLayout(capture_row)
        audio_layout.addWidget(action_button("오디오 파일 가져오기", self.import_audio))
        refine_row = QHBoxLayout()
        refine_row.setSpacing(7)
        refine_row.addWidget(action_button("볼륨 보정", self.refine_volume))
        refine_row.addWidget(action_button("노이즈 제거", self.refine_noise))
        audio_layout.addLayout(refine_row)
        audio_layout.addStretch()
        audio_layout.addWidget(
            action_button(
                "녹음 폴더 열기  →",
                lambda: self.open_folder("recordings"),
                "FolderLink",
            )
        )
        workflow.addWidget(audio_stage, 4)

        divider = QFrame()
        divider.setObjectName("WorkflowDivider")
        workflow.addWidget(divider)

        transcript_stage, transcript_layout = workflow_stage(
            "STEP 02",
            "전사",
            "음성을 글로 옮긴 뒤 문장과 용어를 다듬습니다.",
        )
        transcript_layout.addWidget(
            action_button("전사 시작", self.transcribe, "WorkflowAccent")
        )
        transcript_layout.addWidget(action_button("전사문 다듬기", self.refine_transcript))
        transcript_layout.addStretch()
        transcript_layout.addWidget(
            action_button(
                "전사문 폴더 열기  →",
                lambda: self.open_folder("transcripts"),
                "FolderLink",
            )
        )
        workflow.addWidget(transcript_stage, 3)

        divider = QFrame()
        divider.setObjectName("WorkflowDivider")
        workflow.addWidget(divider)

        note_stage, note_layout = workflow_stage(
            "STEP 03",
            "복습 노트",
            "자료를 더하고 결과를 확인한 뒤 노트로 저장합니다.",
        )
        note_layout.addWidget(action_button("강의 자료 첨부", self.import_material))
        note_layout.addWidget(action_button("노트 미리보기", self.preview_notes))
        note_layout.addWidget(action_button("노트 저장", self.save_notes, "WorkflowAccent"))
        note_layout.addStretch()
        note_layout.addWidget(
            action_button(
                "노트 폴더 열기  →",
                lambda: self.open_folder("notes"),
                "FolderLink",
            )
        )
        workflow.addWidget(note_stage, 3)
        detail_layout.addWidget(action_panel)
        self.tabs = QTabWidget()
        self.transcript_view = QTextBrowser()
        self.note_view = QTextBrowser()
        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        self.tabs.addTab(self.transcript_view, "전사문")
        self.tabs.addTab(self.note_view, "노트")
        self.tabs.addTab(self.raw_view, "메타데이터")
        detail_layout.addWidget(self.tabs)
        content.addWidget(detail, 3)
        outer.addLayout(content)
        self._set_actions_enabled(False)
        self.tabs.setEnabled(False)

    def refresh(self, *_args: object) -> None:
        selected = self.current_session_id
        rows = self.window.container.session.session_history().payload["sessions"]
        query = self.search.text().strip().lower()
        if query:
            rows = [row for row in rows if query in " ".join(str(row.get(k) or "") for k in ("session_id", "title", "course")).lower()]
        self.list.blockSignals(True)
        self.list.clear()
        selected_item = None
        for row in rows:
            text = (
                f"{row['date']}  {row.get('title') or row['session_id']}\n"
                f"{row.get('course') or '과목 없음'} · {format_status(row.get('status'))}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, row["session_id"])
            self.list.addItem(item)
            if row["session_id"] == selected:
                selected_item = item
        self.list.blockSignals(False)
        if selected_item:
            self.list.setCurrentItem(selected_item)
        elif self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._show_session(None)

    def select_session(self, session_id: str) -> None:
        self.current_session_id = session_id
        self.refresh()

    def _selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self._show_session(str(current.data(Qt.UserRole)) if current else None)

    def _show_session(self, session_id: str | None) -> None:
        self.current_session_id = session_id
        self._set_actions_enabled(bool(session_id))
        if not session_id:
            self.detail_title.setText("세션을 선택하세요")
            self.detail_meta.setText("왼쪽 목록에서 세션을 선택하면 작업 도구와 결과물을 확인할 수 있습니다.")
            self.raw_view.clear()
            self.transcript_view.clear()
            self.note_view.clear()
            self.tabs.setEnabled(False)
            return
        session = self.window.container.session.session_detail(session_id).payload
        self.tabs.setEnabled(True)
        self.detail_title.setText(str(session.get("title") or session_id))
        self.detail_meta.setText(
            f"{session['date']} · {session.get('course') or '과목 없음'} · {format_status(session.get('status'))}"
        )
        self.raw_view.setPlainText(json.dumps(session, ensure_ascii=False, indent=2))
        self._load_artifact(self.transcript_view, session.get("transcript_file_path"))
        note_rel = self.window.container.session.store.build_note_path(session_id, course=session.get("course"))
        self._load_artifact(self.note_view, note_rel)

    def _load_artifact(self, view: QTextBrowser, relative: str | None) -> None:
        if not relative:
            view.setPlainText("아직 생성되지 않음")
            return
        path = self.window.config.workspace / relative
        if path.exists():
            view.setMarkdown(path.read_text(encoding="utf-8"))
        else:
            view.setPlainText("파일 없음")

    def _set_actions_enabled(self, enabled: bool) -> None:
        for button in self.action_buttons:
            button.setEnabled(enabled)

    def _require_id(self) -> str:
        if not self.current_session_id:
            raise RuntimeError("세션을 선택하세요.")
        return self.current_session_id

    def edit_session(self) -> None:
        sid = self._require_id()
        session = self.window.container.session.session_detail(sid).payload
        dialog = SessionDialog(self, session)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.values()
            self.window.execute(lambda: self.window.container.session.session_update_metadata(sid, date=values["date"], title=values["title"], course=values["course"]))

    def delete_session(self) -> None:
        sid = self._require_id()
        if QMessageBox.question(self, "세션 삭제", f"'{sid}'와 연결 파일을 삭제할까요?") == QMessageBox.Yes:
            self.window.execute(lambda: self.window.container.session.session_delete(sid))
            self.current_session_id = None

    def capture_start(self) -> None:
        sid = self._require_id()
        self.window.run_background("녹음 시작", sid, lambda _t, _p, _j: self.window.container.session.capture_start(sid))

    def capture_stop(self) -> None:
        sid = self._require_id()
        self.window.run_background("녹음 중지", sid, lambda _t, _p, _j: self.window.container.session.capture_stop(sid))

    def import_audio(self) -> None:
        sid = self._require_id()
        path, _ = QFileDialog.getOpenFileName(self, "오디오 가져오기", "", "Audio (*.wav *.mp3)")
        if path:
            self.window.run_background("오디오 가져오기", sid, lambda _t, _p, _j: self.window.container.session.import_audio(sid, path))

    def import_material(self) -> None:
        sid = self._require_id()
        path, _ = QFileDialog.getOpenFileName(self, "자료 첨부", "", "Documents (*.pdf *.ppt *.pptx)")
        if path:
            self.window.run_background("자료 첨부", sid, lambda _t, _p, _j: self.window.container.session.import_material(sid, path))

    def refine_volume(self) -> None:
        sid = self._require_id()
        self.window.run_background("볼륨 보정", sid, lambda _t, _p, _j: self.window.container.session.refine_audio_volume(sid))

    def refine_noise(self) -> None:
        sid = self._require_id()
        if not self.window.ensure_local_feature("deepfilter"):
            return
        self.window.run_background(
            "노이즈 제거",
            sid,
            lambda token, progress, job: self.window.container.session.refine_audio_noise(
                sid,
                progress_callback=progress,
                cancellation_token=token,
                job_id=job,
            ),
        )

    def transcribe(self) -> None:
        sid = self._require_id()
        if not self.window.ensure_provider_credentials("stt"):
            return
        if self.window.config.stt.mode == "local" and not self.window.ensure_local_feature("whisper"):
            return
        self.window.run_background("전사", sid, lambda token, progress, job: self.window.container.session.transcribe_session(sid, cancellation_token=token, progress_callback=progress, job_id=job))

    def refine_transcript(self) -> None:
        sid = self._require_id()
        if not self.window.ensure_provider_credentials("llm"):
            return
        self.window.run_background("전사문 refine", sid, lambda token, progress, job: self.window.container.session.transcript_refine(sid, cancellation_token=token, progress_callback=progress, job_id=job))

    def preview_notes(self) -> None:
        sid = self._require_id()
        if not self.window.ensure_provider_credentials("llm"):
            return
        self.window.run_background("노트 미리보기", sid, lambda token, progress, job: self.window.container.session.summarize_session(sid, preview=True, cancellation_token=token, progress_callback=progress, job_id=job))

    def save_notes(self) -> None:
        sid = self._require_id()
        if not self.window.ensure_provider_credentials("llm"):
            return
        self.window.run_background("노트 저장", sid, lambda token, progress, job: self.window.container.session.summarize_session(sid, preview=False, cancellation_token=token, progress_callback=progress, job_id=job))

    def open_folder(self, kind: str) -> None:
        sid = self._require_id()
        self.window.execute(lambda: self.window.container.library.library_open(sid, open_transcript=kind == "transcripts", open_recordings=kind == "recordings"), refresh=False)


class LibraryPage(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.setObjectName("Page")
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        eyebrow = QLabel("ARCHIVE")
        eyebrow.setObjectName("PageEyebrow")
        layout.addWidget(eyebrow)
        layout.addSpacing(7)
        title = QLabel("강의 보관함")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        layout.addSpacing(5)
        subtitle = QLabel("완료된 세션과 노트 내용을 빠르게 찾아봅니다.")
        subtitle.setObjectName("Muted")
        layout.addWidget(subtitle)
        layout.addSpacing(24)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.query = QLineEdit()
        self.query.setPlaceholderText("세션 ID 또는 노트 내용 검색")
        self.query.setClearButtonEnabled(True)
        self.query.returnPressed.connect(self.refresh)
        button = QPushButton("검색")
        button.clicked.connect(self.refresh)
        row.addWidget(self.query)
        row.addWidget(button)
        layout.addLayout(row)
        layout.addSpacing(12)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "날짜", "제목", "과목", "상태"])
        configure_session_table(self.table)
        layout.addWidget(self.table)
        self.empty_state = EmptyState(
            "보관함이 비어 있습니다",
            "세션을 만들고 전사나 노트를 저장하면 이곳에서 검색할 수 있습니다.",
        )
        layout.addWidget(self.empty_state, 1)
        layout.addSpacing(10)
        open_row = QHBoxLayout()
        self.open_buttons: list[QPushButton] = []
        for label, kind in (("노트 폴더", "notes"), ("전사문 폴더", "transcripts"), ("녹음 폴더", "recordings")):
            action = QPushButton(label)
            action.clicked.connect(lambda _checked=False, value=kind: self.open_selected(value))
            open_row.addWidget(action)
            self.open_buttons.append(action)
        open_row.addStretch()
        layout.addLayout(open_row)

    def refresh(self) -> None:
        selected_item = self.table.item(self.table.currentRow(), 0)
        selected_session_id = selected_item.text() if selected_item else None
        query = self.query.text().strip()
        result = self.window.container.library.library_search(query) if query else self.window.container.library.library_list(sort_recent=True)
        sessions = result.payload["sessions"]
        fill_session_table(self.table, sessions)
        has_sessions = bool(sessions)
        self.table.setVisible(has_sessions)
        self.empty_state.setVisible(not has_sessions)
        for button in self.open_buttons:
            button.setEnabled(has_sessions)
        if has_sessions:
            selected_row = next(
                (
                    row
                    for row in range(self.table.rowCount())
                    if self.table.item(row, 0)
                    and self.table.item(row, 0).text() == selected_session_id
                ),
                0,
            )
            self.table.selectRow(selected_row)

    def open_selected(self, kind: str) -> None:
        selected_row = self.table.currentRow()
        if selected_row < 0 and self.table.rowCount() > 0:
            selected_row = 0
            self.table.selectRow(selected_row)
        item = self.table.item(selected_row, 0)
        if not item:
            return
        self.window.execute(lambda: self.window.container.library.library_open(item.text(), open_transcript=kind == "transcripts", open_recordings=kind == "recordings"), refresh=False)


class SettingsPage(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.setObjectName("Page")
        self.window = window
        self._runtime_probe_requested = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        eyebrow = QLabel("PREFERENCES")
        eyebrow.setObjectName("PageEyebrow")
        outer.addWidget(eyebrow)
        outer.addSpacing(7)
        title = QLabel("앱 설정")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        outer.addSpacing(5)
        subtitle = QLabel("녹음 환경과 전사·노트 생성 방식을 설정합니다.")
        subtitle.setObjectName("Muted")
        outer.addWidget(subtitle)
        outer.addSpacing(20)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("SettingsPanel")
        form = QFormLayout(body)
        form.setContentsMargins(22, 20, 22, 24)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow(settings_section("일반 및 녹음"))
        self.workspace = QLineEdit()
        workspace_row = QHBoxLayout()
        workspace_row.addWidget(self.workspace)
        choose = QPushButton("찾기")
        choose.clicked.connect(self.choose_workspace)
        workspace_row.addWidget(choose)
        form.addRow("Workspace", workspace_row)
        self.language = combo((("한국어", "ko"), ("English", "en")))
        self.audio_format = combo((("WAV", "wav"), ("MP3", "mp3")))
        self.capture_source = combo((("마이크", "microphone"), ("시스템 오디오", "system_audio")))
        self.capture_source.currentIndexChanged.connect(self.refresh_devices)
        self.devices = NoWheelComboBox()
        device_row = QHBoxLayout()
        device_row.addWidget(self.devices)
        device_refresh = QPushButton("장치 새로고침")
        device_refresh.clicked.connect(self.refresh_devices)
        device_row.addWidget(device_refresh)
        form.addRow("UI 언어", self.language)
        form.addRow("오디오 형식", self.audio_format)
        form.addRow("녹음 소스", self.capture_source)
        form.addRow("녹음 장치", device_row)
        form.addRow(settings_section("전사 및 오디오 처리"))
        self.stt_mode = combo((("API", "api"), ("로컬 Whisper", "local")))
        self.stt_provider = combo((("OpenAI-compatible", "openai-compatible"), ("Deepgram", "deepgram")))
        self.stt_key = QLineEdit()
        self.stt_key.setEchoMode(QLineEdit.Password)
        self.stt_model = combo(
            tuple(
                (f"{name} — {recommendation}", name)
                for name, recommendation in LOCAL_MODEL_RECOMMENDATIONS
            )
        )
        self.stt_language = QLineEdit()
        self.stt_device = combo(tuple((name, name) for name in ("auto", "cpu", "cuda")))
        self.stt_compute_type = combo(
            tuple(
                (name, name)
                for name in ("auto", "int8", "int8_float16", "float16", "float32")
            )
        )
        self.stt_batch_size = NoWheelSpinBox(); self.stt_batch_size.setRange(1, 64)
        self.stt_beam_size = NoWheelSpinBox(); self.stt_beam_size.setRange(1, 20)
        self.stt_temperature = QLineEdit()
        self.stt_temperature.setPlaceholderText("비움 = runtime 기본값")
        self.stt_vad_filter = QCheckBox()
        self.stt_vad_min_silence = NoWheelSpinBox(); self.stt_vad_min_silence.setRange(1, 10000)
        self.stt_condition_previous = QCheckBox()
        self.stt_word_timestamps = QCheckBox()
        self.stt_hotwords = QLineEdit()
        self.stt_cpu_threads = NoWheelSpinBox(); self.stt_cpu_threads.setRange(0, 256)
        self.stt_num_workers = NoWheelSpinBox(); self.stt_num_workers.setRange(1, 32)
        self.stt_quality_retry = QCheckBox()
        self.stt_quality_retry_model = QLineEdit()
        self.stt_quality_retry_model.setPlaceholderText("비움 = 1차 모델 재사용")
        self.stt_quality_retry_beam = NoWheelSpinBox(); self.stt_quality_retry_beam.setRange(1, 20)
        self.stt_quality_retry_context = NoWheelDoubleSpinBox(); self.stt_quality_retry_context.setRange(0.0, 10.0); self.stt_quality_retry_context.setDecimals(1)
        self.stt_quality_retry_windows = NoWheelSpinBox(); self.stt_quality_retry_windows.setRange(0, 64)
        self.stt_quality_retry_seconds = NoWheelDoubleSpinBox(); self.stt_quality_retry_seconds.setRange(0.0, 3600.0); self.stt_quality_retry_seconds.setDecimals(1)
        self.dynaudnorm = QCheckBox()
        self.dynaudnorm_f = NoWheelSpinBox(); self.dynaudnorm_f.setRange(10, 8000)
        self.dynaudnorm_g = NoWheelSpinBox(); self.dynaudnorm_g.setRange(3, 301); self.dynaudnorm_g.setSingleStep(2)
        self.gain_db = NoWheelDoubleSpinBox(); self.gain_db.setRange(-60.0, 60.0); self.gain_db.setDecimals(1)
        form.addRow("STT 방식", self.stt_mode)
        form.addRow("STT API provider", self.stt_provider)
        form.addRow("STT API key", self.stt_key)
        form.addRow("Whisper 모델", self.stt_model)
        form.addRow("STT 언어", self.stt_language)
        form.addRow("로컬 device", self.stt_device)
        form.addRow("Compute type", self.stt_compute_type)
        form.addRow("Batch size", self.stt_batch_size)
        form.addRow("Beam size", self.stt_beam_size)
        form.addRow("Temperature", self.stt_temperature)
        form.addRow("VAD", self.stt_vad_filter)
        form.addRow("VAD 최소 무음 (ms)", self.stt_vad_min_silence)
        form.addRow("이전 문맥 사용", self.stt_condition_previous)
        form.addRow("단어 timestamp", self.stt_word_timestamps)
        form.addRow("Hotwords", self.stt_hotwords)
        form.addRow("CPU threads (0=자동)", self.stt_cpu_threads)
        form.addRow("Workers", self.stt_num_workers)
        form.addRow("저신뢰 구간 재전사", self.stt_quality_retry)
        form.addRow("재전사 모델", self.stt_quality_retry_model)
        form.addRow("재전사 beam", self.stt_quality_retry_beam)
        form.addRow("재전사 문맥 (초)", self.stt_quality_retry_context)
        form.addRow("재전사 최대 구간", self.stt_quality_retry_windows)
        form.addRow("재전사 최대 길이 (초)", self.stt_quality_retry_seconds)
        self.stt_hardware_guide = QLabel(LOCAL_STT_HARDWARE_GUIDE)
        self.stt_hardware_guide.setObjectName("SettingsActionBody")
        self.stt_hardware_guide.setWordWrap(True)
        form.addRow("하드웨어별 추천", self.stt_hardware_guide)
        form.addRow("dynaudnorm", self.dynaudnorm)
        form.addRow("dynaudnorm f", self.dynaudnorm_f)
        form.addRow("dynaudnorm g", self.dynaudnorm_g)
        form.addRow("추가 gain (dB)", self.gain_db)
        form.addRow(settings_section("노트 생성 AI"))
        self.llm_provider = combo((("Gemini", "gemini"), ("Ollama", "ollama")))
        self.llm_key = QLineEdit(); self.llm_key.setEchoMode(QLineEdit.Password)
        self.llm_model = QLineEdit()
        self.llm_language = QLineEdit()
        self.thinking = combo(tuple((value, value) for value in ("minimal", "low", "medium", "high")))
        self.ollama_url = QLineEdit()
        form.addRow("LLM provider", self.llm_provider)
        form.addRow("Gemini API key", self.llm_key)
        form.addRow("LLM 모델", self.llm_model)
        form.addRow("LLM 언어", self.llm_language)
        form.addRow("Thinking level", self.thinking)
        form.addRow("Ollama URL", self.ollama_url)

        def controls_with_labels(*fields: QWidget) -> tuple[QWidget, ...]:
            controls: list[QWidget] = []
            for field in fields:
                controls.append(field)
                label = form.labelForField(field)
                if label is not None:
                    controls.append(label)
            return tuple(controls)

        self._stt_api_controls = controls_with_labels(self.stt_provider, self.stt_key)
        self._stt_local_controls = controls_with_labels(
            self.stt_model,
            self.stt_device,
            self.stt_compute_type,
            self.stt_batch_size,
            self.stt_beam_size,
            self.stt_temperature,
            self.stt_vad_filter,
            self.stt_vad_min_silence,
            self.stt_condition_previous,
            self.stt_word_timestamps,
            self.stt_hotwords,
            self.stt_cpu_threads,
            self.stt_num_workers,
            self.stt_quality_retry,
            self.stt_quality_retry_model,
            self.stt_quality_retry_beam,
            self.stt_quality_retry_context,
            self.stt_quality_retry_windows,
            self.stt_quality_retry_seconds,
            self.stt_hardware_guide,
        )
        self._gemini_controls = controls_with_labels(self.llm_key)
        self._ollama_controls = controls_with_labels(self.ollama_url)
        self.stt_mode.currentIndexChanged.connect(self._sync_provider_fields)
        self.llm_provider.currentIndexChanged.connect(self._sync_provider_fields)

        form.addRow(settings_section("로컬 처리 환경"))
        runtime_panel = QFrame()
        runtime_panel.setObjectName("SettingsActionPanel")
        runtime_panel_layout = QHBoxLayout(runtime_panel)
        runtime_panel_layout.setContentsMargins(18, 16, 18, 17)
        runtime_panel_layout.setSpacing(18)

        runtime_status_column = QVBoxLayout()
        runtime_status_column.setSpacing(6)
        runtime_title = QLabel("기능 애드온 상태")
        runtime_title.setObjectName("SettingsActionTitle")
        runtime_description = QLabel("로컬 전사와 오디오 정제에 필요한 구성요소를 확인합니다.")
        runtime_description.setObjectName("SettingsActionBody")
        runtime_description.setWordWrap(True)
        runtime_status_column.addWidget(runtime_title)
        runtime_status_column.addWidget(runtime_description)
        runtime_status_column.addSpacing(6)
        self.runtime_python_status = QLabel("확인 전")
        self.runtime_whisper_status = QLabel("확인 전")
        self.runtime_deepfilter_status = QLabel("확인 전")
        self.runtime_gemini_status = QLabel("확인 전")
        self.runtime_path_status = QLabel("-")
        self.runtime_path_status.setObjectName("SettingsPath")
        self.runtime_path_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.runtime_error_status = QLabel("-")
        self.runtime_error_status.setObjectName("SettingsPath")
        self.runtime_error_status.setWordWrap(True)

        runtime_status_grid = QGridLayout()
        runtime_status_grid.setHorizontalSpacing(12)
        runtime_status_grid.setVerticalSpacing(6)
        runtime_statuses = (
            ("관리형 Python", self.runtime_python_status),
            ("Whisper", self.runtime_whisper_status),
            ("DeepFilterNet", self.runtime_deepfilter_status),
            ("Gemini SDK", self.runtime_gemini_status),
        )
        for row_index, (label, value) in enumerate(runtime_statuses):
            field_label = QLabel(label)
            field_label.setObjectName("SettingsFieldLabel")
            runtime_status_grid.addWidget(field_label, row_index, 0)
            runtime_status_grid.addWidget(value, row_index, 1)
        runtime_status_column.addLayout(runtime_status_grid)
        runtime_status_column.addSpacing(3)
        runtime_status_column.addWidget(self.runtime_path_status)
        runtime_status_column.addWidget(self.runtime_error_status)
        runtime_panel_layout.addLayout(runtime_status_column, 3)

        runtime_divider = QFrame()
        runtime_divider.setObjectName("SettingsDivider")
        runtime_panel_layout.addWidget(runtime_divider)

        runtime_action_column = QVBoxLayout()
        runtime_action_column.setSpacing(7)
        action_title = QLabel("설치할 기능")
        action_title.setObjectName("SettingsActionTitle")
        runtime_action_column.addWidget(action_title)
        self.runtime_feature = combo(
            (
                ("Whisper 전사", "whisper"),
                ("DeepFilterNet 노이즈 제거", "deepfilter"),
                ("Gemini SDK", "gemini"),
                ("전체 기능", "all"),
            )
        )
        runtime_action_column.addWidget(self.runtime_feature)
        install_runtime = QPushButton("선택 항목 설치")
        install_runtime.setObjectName("SettingsAccent")
        install_runtime.clicked.connect(self.install_selected_runtime)
        runtime_action_column.addWidget(install_runtime)
        probe = QPushButton("상태 다시 확인")
        probe.clicked.connect(self.probe_runtime)
        runtime_action_column.addWidget(probe)
        runtime_action_column.addSpacing(3)
        maintenance = QHBoxLayout()
        maintenance.setSpacing(2)
        repair = QPushButton("설치 복구")
        repair.setObjectName("SettingsLink")
        repair.clicked.connect(self.repair_runtime)
        external = QPushButton("외부 Python")
        external.setObjectName("SettingsLink")
        external.clicked.connect(self.choose_external_python)
        remove_runtime = QPushButton("Runtime 제거")
        remove_runtime.setObjectName("SettingsDangerLink")
        remove_runtime.clicked.connect(self.remove_runtime)
        maintenance.addWidget(repair, 1)
        maintenance.addWidget(external, 1)
        maintenance.addWidget(remove_runtime, 1)
        runtime_action_column.addLayout(maintenance)
        runtime_action_column.addStretch()
        runtime_panel_layout.addLayout(runtime_action_column, 2)
        form.addRow(runtime_panel)

        form.addRow(settings_section("로컬 모델"))
        model_panel = QFrame()
        model_panel.setObjectName("SettingsActionPanel")
        model_layout = QHBoxLayout(model_panel)
        model_layout.setContentsMargins(18, 16, 18, 17)
        model_layout.setSpacing(18)

        whisper_column = QVBoxLayout()
        whisper_title = QLabel("Whisper 모델")
        whisper_title.setObjectName("SettingsActionTitle")
        whisper_body = QLabel("위에서 선택한 모델을 미리 받아 로컬 전사를 준비합니다.")
        whisper_body.setObjectName("SettingsActionBody")
        whisper_body.setWordWrap(True)
        whisper_column.addWidget(whisper_title)
        whisper_column.addWidget(whisper_body)
        whisper_actions = QHBoxLayout()
        install = QPushButton("모델 받기")
        install.setObjectName("SettingsAccent")
        install.clicked.connect(self.install_whisper)
        remove = QPushButton("모델 삭제")
        remove.setObjectName("SettingsDangerLink")
        remove.clicked.connect(self.delete_whisper)
        whisper_actions.addWidget(install, 1)
        whisper_actions.addWidget(remove, 1)
        whisper_column.addSpacing(8)
        whisper_column.addLayout(whisper_actions)
        whisper_column.addStretch()
        model_layout.addLayout(whisper_column, 1)

        model_divider = QFrame()
        model_divider.setObjectName("SettingsDivider")
        model_layout.addWidget(model_divider)

        ollama_column = QVBoxLayout()
        ollama_title = QLabel("Ollama 모델")
        ollama_title.setObjectName("SettingsActionTitle")
        ollama_body = QLabel("Ollama 연결을 확인하거나 사용할 모델을 내려받습니다.")
        ollama_body.setObjectName("SettingsActionBody")
        ollama_body.setWordWrap(True)
        ollama_column.addWidget(ollama_title)
        ollama_column.addWidget(ollama_body)
        ollama_actions = QHBoxLayout()
        ollama = QPushButton("연결 확인")
        ollama.clicked.connect(self.check_ollama)
        pull = QPushButton("모델 받기")
        pull.setObjectName("SettingsAccent")
        pull.clicked.connect(self.pull_ollama)
        ollama_actions.addWidget(ollama)
        ollama_actions.addWidget(pull)
        ollama_column.addSpacing(8)
        ollama_column.addLayout(ollama_actions)
        ollama_column.addStretch()
        model_layout.addLayout(ollama_column, 1)
        form.addRow(model_panel)

        save = QPushButton("설정 저장")
        save.setObjectName("Primary")
        save.clicked.connect(self.save)
        form.addRow(save)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def refresh(self) -> None:
        cfg = self.window.config
        self.workspace.setText(str(cfg.workspace))
        set_combo(self.language, cfg.ui_language)
        set_combo(self.audio_format, cfg.audio_format)
        set_combo(self.capture_source, cfg.capture_source)
        set_combo(self.stt_mode, cfg.stt.mode)
        set_combo(self.stt_provider, cfg.stt.api_provider)
        set_combo(self.stt_model, cfg.stt.local_model_name)
        self.stt_language.setText(cfg.stt.language or "")
        set_combo(self.stt_device, cfg.stt.local_device)
        set_combo(self.stt_compute_type, cfg.stt.compute_type)
        self.stt_batch_size.setValue(cfg.stt.batch_size)
        self.stt_beam_size.setValue(cfg.stt.beam_size)
        self.stt_temperature.setText(
            "" if cfg.stt.temperature is None else str(cfg.stt.temperature)
        )
        self.stt_vad_filter.setChecked(cfg.stt.vad_filter)
        self.stt_vad_min_silence.setValue(cfg.stt.vad_min_silence_duration_ms)
        self.stt_condition_previous.setChecked(cfg.stt.condition_on_previous_text)
        self.stt_word_timestamps.setChecked(cfg.stt.word_timestamps)
        self.stt_hotwords.setText(cfg.stt.hotwords or "")
        self.stt_cpu_threads.setValue(cfg.stt.cpu_threads)
        self.stt_num_workers.setValue(cfg.stt.num_workers)
        self.stt_quality_retry.setChecked(cfg.stt.quality_retry_enabled)
        self.stt_quality_retry_model.setText(cfg.stt.quality_retry_model or "")
        self.stt_quality_retry_beam.setValue(cfg.stt.quality_retry_beam_size)
        self.stt_quality_retry_context.setValue(cfg.stt.quality_retry_context_seconds)
        self.stt_quality_retry_windows.setValue(cfg.stt.quality_retry_max_windows)
        self.stt_quality_retry_seconds.setValue(cfg.stt.quality_retry_max_seconds)
        self.dynaudnorm.setChecked(cfg.stt.use_dynaudnorm)
        self.dynaudnorm_f.setValue(cfg.stt.dynaudnorm_f or 150)
        self.dynaudnorm_g.setValue(cfg.stt.dynaudnorm_g or 15)
        self.gain_db.setValue(cfg.stt.gain_db or 0.0)
        set_combo(self.llm_provider, cfg.llm.provider)
        self.llm_model.setText(cfg.llm.model_name)
        self.llm_language.setText(cfg.llm.language or "")
        set_combo(self.thinking, cfg.llm.thinking_level)
        self.ollama_url.setText(cfg.llm.ollama_base_url)
        self.stt_key.clear(); self.stt_key.setPlaceholderText("저장됨" if cfg.stt.api_key else "")
        self.llm_key.clear(); self.llm_key.setPlaceholderText("저장됨" if cfg.llm.api_key else "")
        self._sync_provider_fields()
        self.refresh_devices()
        if not self._runtime_probe_requested:
            self._runtime_probe_requested = True
            QTimer.singleShot(0, self.probe_runtime)

    def _sync_provider_fields(self, *_args: object) -> None:
        stt_uses_api = self.stt_mode.currentData() == "api"
        for control in self._stt_api_controls:
            control.setEnabled(stt_uses_api)
        for control in self._stt_local_controls:
            control.setEnabled(not stt_uses_api)

        llm_uses_gemini = self.llm_provider.currentData() == "gemini"
        for control in self._gemini_controls:
            control.setEnabled(llm_uses_gemini)
        for control in self._ollama_controls:
            control.setEnabled(not llm_uses_gemini)

    def set_runtime_status(self, status: RuntimeStatus) -> None:
        self.runtime_python_status.setText(
            f"{status.python_version or '설치되지 않음'} · {status.architecture or '-'} · {status.source}"
        )
        self.runtime_whisper_status.setText(
            f"설치됨 · {status.whisper_version or 'version unknown'}" if status.whisper_installed else "설치되지 않음"
        )
        self.runtime_deepfilter_status.setText(
            f"설치됨 · {status.deepfilter_version or 'version unknown'}" if status.deepfilter_installed else "설치되지 않음"
        )
        self.runtime_gemini_status.setText(
            f"설치됨 · {status.gemini_version or 'version unknown'}" if status.gemini_installed else "설치되지 않음"
        )
        self.runtime_path_status.setText(status.python_path or "-")
        self.runtime_error_status.setText(status.error or "없음")

    def _runtime_progress(self, emit, job_id: str):
        def callback(stage, completed, total, message) -> None:
            emit(TaskEvent(job_id, None, stage, completed, total, message))
        return callback

    def _confirm_runtime_install(self, feature: str) -> bool:
        estimates = {
            "whisper": "약 300MB~1GB (모델 weights 별도)",
            "deepfilter": "약 1.5~3GB",
            "gemini": "약 50~150MB",
            "all": "약 2~4GB",
        }
        message = (
            f"다운로드 예상 크기: {estimates[feature]}\n"
            f"설치 위치: {self.window.container.runtime.runtime_dir}\n\n설치를 시작할까요?"
        )
        return QMessageBox.question(self, "로컬 AI 설치", message) == QMessageBox.Yes

    def _install_runtime(self, feature: str) -> None:
        if not self._confirm_runtime_install(feature):
            return
        manager = self.window.container.runtime
        def work(token, emit, job_id):
            kwargs = {"progress": self._runtime_progress(emit, job_id), "cancellation_token": token}
            if feature == "whisper":
                return manager.install_whisper(**kwargs)
            if feature == "deepfilter":
                return manager.install_deepfilter(**kwargs)
            if feature == "gemini":
                return manager.install_gemini(**kwargs)
            return manager.install_all(**kwargs)
        self.window.run_background(f"애드온 {feature} 설치", "__runtime__", work)

    def install_whisper_runtime(self) -> None:
        self._install_runtime("whisper")

    def install_deepfilter_runtime(self) -> None:
        self._install_runtime("deepfilter")

    def install_gemini_runtime(self) -> None:
        self._install_runtime("gemini")

    def install_all_runtime(self) -> None:
        self._install_runtime("all")

    def install_selected_runtime(self) -> None:
        self._install_runtime(str(self.runtime_feature.currentData()))

    def probe_runtime(self) -> None:
        self.window.run_background(
            "로컬 AI 상태 확인",
            None,
            lambda _token, _emit, _job: self.window.container.runtime.probe(),
            block_close=False,
        )

    def repair_runtime(self) -> None:
        manager = self.window.container.runtime
        self.window.run_background(
            "로컬 AI 설치 복구",
            "__runtime__",
            lambda token, emit, job: manager.repair(
                progress=self._runtime_progress(emit, job), cancellation_token=token
            ),
        )

    def remove_runtime(self) -> None:
        if QMessageBox.question(self, "Runtime 제거", "관리형 로컬 AI runtime을 제거할까요? 모델 cache는 유지됩니다.") != QMessageBox.Yes:
            return
        self.window.run_background("로컬 AI runtime 제거", "__runtime__", lambda _token, _emit, _job: self.window.container.runtime.remove())

    def choose_external_python(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "외부 Python executable 선택")
        if path:
            self.window.run_background("외부 Python 검증", None, lambda _token, _emit, _job: self.window.container.runtime.set_external_python(path))

    def choose_workspace(self) -> None:
        value = QFileDialog.getExistingDirectory(self, "Workspace 선택", self.workspace.text())
        if value:
            previous = self.workspace.text()
            self.workspace.setText(value)
            if self._save(show_confirmation=False):
                self.window.show_status_message(
                    f"워크스페이스를 변경했습니다: {self.window.config.workspace}",
                    7000,
                )
            else:
                self.workspace.setText(previous)

    def refresh_devices(self) -> None:
        self.devices.clear()
        try:
            runtime = self.window.container.session.runtime_adapter
            devices = runtime.list_devices()
            source = self.capture_source.currentData()
            for device in devices:
                if device.source == source:
                    self.devices.addItem(device.name, device)
            if not self.devices.count():
                self.devices.addItem("사용 가능한 장치 없음", None)
            for index in range(self.devices.count()):
                device = self.devices.itemData(index)
                if device and (device.id == self.window.config.capture_device_id or device.name == self.window.config.capture_device_name):
                    self.devices.setCurrentIndex(index)
                    break
        except Exception as exc:
            self.devices.addItem(f"장치 확인 실패: {exc}", None)

    def save(self) -> None:
        self._save(show_confirmation=True)

    def _save(self, *, show_confirmation: bool) -> bool:
        old = self.window.config
        device: AudioDevice | None = self.devices.currentData()
        stt_mode = str(self.stt_mode.currentData())
        llm_provider = str(self.llm_provider.currentData())
        stt_api_key = self.stt_key.text().strip() or old.stt.api_key
        gemini_api_key = self.llm_key.text().strip() or old.llm.api_key
        config = AppConfig(
            workspace=Path(self.workspace.text()),
            ui_language=str(self.language.currentData()),
            audio_format=str(self.audio_format.currentData()),
            capture_source=str(self.capture_source.currentData()),
            capture_device_id=device.id if device else None,
            capture_device_name=device.name if device else None,
            capture_backend=device.backend if device else None,
            stt=STTConfig(
                mode=stt_mode,
                api_provider=str(self.stt_provider.currentData()),
                api_key=stt_api_key,
                local_model_name=str(self.stt_model.currentData()),
                language=self.stt_language.text().strip() or None,
                local_device=str(self.stt_device.currentData()),
                compute_type=str(self.stt_compute_type.currentData()),
                batch_size=self.stt_batch_size.value(),
                beam_size=self.stt_beam_size.value(),
                temperature=(
                    float(self.stt_temperature.text())
                    if self.stt_temperature.text().strip()
                    else None
                ),
                vad_filter=self.stt_vad_filter.isChecked(),
                vad_min_silence_duration_ms=self.stt_vad_min_silence.value(),
                condition_on_previous_text=self.stt_condition_previous.isChecked(),
                word_timestamps=self.stt_word_timestamps.isChecked(),
                hotwords=self.stt_hotwords.text().strip() or None,
                cpu_threads=self.stt_cpu_threads.value(),
                num_workers=self.stt_num_workers.value(),
                quality_retry_enabled=self.stt_quality_retry.isChecked(),
                quality_retry_model=self.stt_quality_retry_model.text().strip() or None,
                quality_retry_beam_size=self.stt_quality_retry_beam.value(),
                quality_retry_context_seconds=self.stt_quality_retry_context.value(),
                quality_retry_max_windows=self.stt_quality_retry_windows.value(),
                quality_retry_max_seconds=self.stt_quality_retry_seconds.value(),
                use_dynaudnorm=self.dynaudnorm.isChecked(),
                dynaudnorm_f=self.dynaudnorm_f.value(),
                dynaudnorm_g=self.dynaudnorm_g.value() | 1,
                gain_db=self.gain_db.value(),
            ),
            llm=LLMConfig(
                provider=llm_provider,
                api_key=gemini_api_key,
                model_name=self.llm_model.text().strip(),
                thinking_level=str(self.thinking.currentData()),
                language=self.llm_language.text().strip() or None,
                ollama_base_url=self.ollama_url.text().strip() or "http://localhost:11434",
            ),
        )
        try:
            config.workspace = ensure_workspace_structure(config.workspace)
            self.window.repository.save(config)
            self.window.reload_services(config)
            if show_confirmation:
                QMessageBox.information(self, "설정", "설정을 저장했습니다.")
            return True
        except Exception as exc:
            self.window.show_error(exc)
            return False

    def install_whisper(self) -> None:
        name = str(self.stt_model.currentData())
        self.window.run_background(f"Whisper {name} 설치", None, lambda token, _progress, _job: self.window.container.models.install_whisper(name, cancellation_token=token))

    def delete_whisper(self) -> None:
        name = str(self.stt_model.currentData())
        if QMessageBox.question(self, "모델 삭제", f"Whisper {name} 모델을 삭제할까요?") == QMessageBox.Yes:
            self.window.execute(lambda: self.window.container.models.delete_whisper(name), refresh=False)

    def check_ollama(self) -> None:
        def work(_token: object, _progress: object, _job: str) -> object:
            if not self.window.container.models.ollama_health():
                raise RuntimeError("Ollama 서버에 연결할 수 없습니다. Ollama를 설치하고 실행하세요.")
            return self.window.container.models.list_ollama_models()
        self.window.run_background("Ollama 확인", None, work)

    def pull_ollama(self) -> None:
        name, accepted = QInputDialog.getText(self, "Ollama 모델", "모델 이름")
        if accepted and name.strip():
            self.window.run_background(f"Ollama {name.strip()} 받기", None, lambda token, _progress, _job: self.window.container.models.pull_ollama(name.strip(), cancellation_token=token))


class MainWindow(QMainWindow):
    def __init__(self, repository: ConfigRepository, config: AppConfig) -> None:
        super().__init__()
        self.repository = repository
        self.config = config
        self.container: ServiceContainer = build_service_container(config)
        self.recovered_recordings = self.container.session.recover_stale_recordings()
        self.translator = Translator(config.ui_language)
        self.jobs = JobController(self)
        self.jobs.progress.connect(self._job_progress)
        self.jobs.succeeded.connect(self._job_success)
        self.jobs.failed.connect(self._job_failure)
        self.jobs.active_changed.connect(self._active_changed)
        self._job_items: dict[str, QListWidgetItem] = {}
        self._job_labels: dict[str, str] = {}
        self.setWindowTitle("Lecture Auto")
        self.resize(1280, 820)
        self._build_ui()
        self.refresh_all()
        if self.recovered_recordings:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "녹음 복구", "중단된 녹음 상태를 복구했습니다: " + ", ".join(self.recovered_recordings)))

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(216)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 26, 18, 20)
        side_layout.setSpacing(4)
        brand = QLabel("Lecture\nAuto")
        brand.setObjectName("BrandMark")
        side_layout.addWidget(brand)
        side_layout.addSpacing(28)
        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(("홈", "세션 관리", "강의 보관함", "설정")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=index: self.show_page(value))
            side_layout.addWidget(button)
            self.nav_buttons.append(button)
        side_layout.addStretch()
        root_layout.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(34, 28, 34, 20)
        main.setSpacing(16)
        self.stack = QStackedWidget()
        self.home_page = HomePage(self)
        self.sessions_page = SessionsPage(self)
        self.library_page = LibraryPage(self)
        self.settings_page = SettingsPage(self)
        for page in (self.home_page, self.sessions_page, self.library_page, self.settings_page):
            self.stack.addWidget(page)
        main.addWidget(self.stack, 1)
        self.task_tray = QFrame()
        self.task_tray.setObjectName("TaskTray")
        task_layout = QVBoxLayout(self.task_tray)
        task_layout.setContentsMargins(14, 10, 14, 12)
        task_layout.setSpacing(8)
        task_header = QHBoxLayout()
        self.task_status = QLabel("준비됨")
        self.task_status.setObjectName("StatusReady")
        self._status_message = ""
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status_message)
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 1)
        self.task_progress.setValue(1)
        self.task_progress.setMaximumWidth(280)
        self.task_progress.setVisible(False)
        self.cancel_jobs_button = QPushButton("작업 취소")
        self.cancel_jobs_button.setVisible(False)
        self.cancel_jobs_button.clicked.connect(self.jobs.cancel_all)
        task_header.addWidget(self.task_status)
        task_header.addWidget(self.task_progress)
        task_header.addStretch()
        task_header.addWidget(self.cancel_jobs_button)
        task_layout.addLayout(task_header)
        self.task_list = QListWidget()
        self.task_list.setMaximumHeight(82)
        self.task_list.setVisible(False)
        task_layout.addWidget(self.task_list)
        main.addWidget(self.task_tray)
        root_layout.addLayout(main, 1)
        self.setCentralWidget(root)
        self.show_page(0)

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()

    def create_session(self) -> None:
        dialog = SessionDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not values["session_id"]:
            QMessageBox.warning(self, "세션", "세션 ID를 입력하세요.")
            return
        result = self.execute(lambda: self.container.session.session_create(**values))
        if result:
            self.sessions_page.select_session(str(values["session_id"]))
            self.show_page(1)

    def execute(self, action: Callable[[], Any], *, refresh: bool = True) -> Any:
        try:
            result = action()
            if isinstance(result, CommandResult):
                self.show_status_message(result.message, 5000)
            if refresh:
                self.refresh_all()
            return result
        except Exception as exc:
            self.show_error(exc)
            return None

    def run_background(
        self,
        label: str,
        session_id: str | None,
        work: Callable[..., Any],
        *,
        block_close: bool = True,
    ) -> None:
        try:
            job_id = self.jobs.submit(
                work,
                session_id=session_id,
                block_close=block_close,
            )
            self._job_labels[job_id] = label
            item = QListWidgetItem(f"{label}: 대기 중")
            item.setData(Qt.UserRole, job_id)
            self.task_list.insertItem(0, item)
            self.task_list.setVisible(True)
            self._job_items[job_id] = item
        except Exception as exc:
            self.show_error(exc)

    @Slot(object)
    def _job_progress(self, event: TaskEvent) -> None:
        item = self._job_items.get(event.job_id)
        label = self._job_labels.get(event.job_id, event.job_id)
        if item:
            item.setText(f"{label}: {event.message or event.stage}")
        if event.total and event.completed is not None:
            self.task_progress.setVisible(True)
            self.task_progress.setRange(0, event.total)
            self.task_progress.setValue(event.completed)
        else:
            self.task_progress.setRange(0, 0)

    @Slot(str, object)
    def _job_success(self, job_id: str, result: object) -> None:
        label = self._job_labels.get(job_id, job_id)
        item = self._job_items.get(job_id)
        message = result.message if isinstance(result, CommandResult) else str(result or "완료")
        if item:
            item.setText(f"{label}: 완료 · {message}")
        if isinstance(result, RuntimeStatus):
            self.settings_page.set_runtime_status(result)
        elif result is None and "runtime 제거" in label:
            self.settings_page.set_runtime_status(self.container.runtime.probe())
        elif isinstance(result, CommandResult) and result.command == "summarize" and result.payload.get("preview"):
            self.sessions_page.note_view.setMarkdown(str(result.payload.get("notes") or result.message))
            self.sessions_page.tabs.setCurrentWidget(self.sessions_page.note_view)
        elif isinstance(result, list):
            QMessageBox.information(self, label, "\n".join(map(str, result)) or "설치된 모델 없음")
        self.refresh_all()

    def ensure_local_feature(self, feature: str) -> bool:
        status = self.container.runtime.probe()
        installed = status.whisper_installed if feature == "whisper" else status.deepfilter_installed
        if installed:
            return True
        label = "Whisper" if feature == "whisper" else "DeepFilterNet"
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Information)
        dialog.setWindowTitle(f"{label} 설치 필요")
        dialog.setText(f"{label} runtime이 설치되지 않았습니다.")
        dialog.setInformativeText("설정의 로컬 AI 섹션에서 설치한 뒤 다시 시도하세요.")
        install = dialog.addButton(f"{label} 설치", QMessageBox.AcceptRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.exec()
        if dialog.clickedButton() is install:
            self.show_page(3)
            if feature == "whisper":
                self.settings_page.install_whisper_runtime()
            else:
                self.settings_page.install_deepfilter_runtime()
        return False

    def ensure_provider_credentials(self, provider_type: str) -> bool:
        if provider_type == "stt":
            if self.config.stt.mode != "api" or self.config.stt.api_key:
                return True
            key = self.repository.get_secret("stt_api_key")
            if key:
                self.config.stt.api_key = key
                self.container.session.stt_config.api_key = key
                return True
            label = "STT API"
        elif provider_type == "llm":
            if self.config.llm.provider != "gemini":
                return True
            if self.config.llm.api_key and self.container.session.llm_adapter is not None:
                return True
            key = self.repository.get_secret("gemini_api_key")
            if key:
                self.config.llm.api_key = key
                self.reload_services(self.config)
                return True
            label = "Gemini API"
        else:
            raise ValueError(f"Unknown provider credential type: {provider_type}")

        QMessageBox.information(
            self,
            f"{label} 키 필요",
            f"{label} 키가 저장되어 있지 않습니다. 설정에서 키를 입력한 뒤 다시 시도하세요.",
        )
        self.show_page(3)
        return False

    @Slot(str, object)
    def _job_failure(self, job_id: str, error: object) -> None:
        label = self._job_labels.get(job_id, job_id)
        item = self._job_items.get(job_id)
        if item:
            item.setText(f"{label}: 실패 · {error}")
        if not isinstance(error, TaskCancelledError):
            self.show_error(error if isinstance(error, BaseException) else RuntimeError(str(error)))

    @Slot(int)
    def _active_changed(self, count: int) -> None:
        self.task_status.setText(f"작업 중 {count}개" if count else "준비됨")
        self.task_progress.setVisible(bool(count))
        self.cancel_jobs_button.setVisible(bool(count))
        if not count:
            self.task_progress.setRange(0, 1)
            self.task_progress.setValue(1)

    def show_status_message(self, message: str, timeout: int = 5000) -> None:
        """Show transient feedback in the task tray without creating a status bar."""
        self._status_message = message
        self.task_status.setText(message)
        if timeout > 0:
            self._status_timer.start(timeout)
        else:
            self._status_timer.stop()

    def _clear_status_message(self) -> None:
        if self.jobs.active_count == 0 and self.task_status.text() == self._status_message:
            self.task_status.setText("준비됨")
        self._status_message = ""

    def show_error(self, exc: BaseException) -> None:
        if isinstance(exc, SessionCommandError):
            text = f"[{exc.code}] {exc.message}\n\n{exc.guidance}"
        else:
            text = str(exc)
        QMessageBox.critical(self, "오류", text)

    def reload_services(self, config: AppConfig) -> None:
        self.container.runtime.close()
        self.config = config
        self.container = build_service_container(config)
        self.translator = Translator(config.ui_language)
        self.refresh_all()

    def refresh_all(self) -> None:
        self.home_page.refresh()
        self.sessions_page.refresh()
        self.library_page.refresh()
        if self.stack.currentWidget() is self.settings_page:
            self.settings_page.refresh()

    def closeEvent(self, event: QCloseEvent) -> None:
        recording = any(row.get("status") == "recording" for row in self.container.session.store.load_all())
        if (recording or self.jobs.has_close_blocking_jobs) and QMessageBox.question(self, "앱 종료", "녹음 또는 작업이 진행 중입니다. 종료할까요?") != QMessageBox.Yes:
            event.ignore()
            return
        self.jobs.cancel_all()
        self.container.runtime.close()
        event.accept()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


def combo(items: tuple[tuple[str, str], ...]) -> QComboBox:
    widget = NoWheelComboBox()
    for label, value in items:
        widget.addItem(label, value)
    return widget


def set_combo(widget: QComboBox, value: object) -> None:
    index = widget.findData(value)
    if index >= 0:
        widget.setCurrentIndex(index)


def settings_section(title: str) -> QLabel:
    label = QLabel(title)
    label.setObjectName("SectionTitle")
    return label


def configure_session_table(table: QTableWidget) -> None:
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(44)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setSectionsClickable(True)
    header.setSectionResizeMode(QHeaderView.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
    header.setSortIndicator(-1, Qt.AscendingOrder)
    table.setSortingEnabled(True)


def format_status(value: object) -> str:
    raw = str(value or "")
    return {
        "idle": "준비",
        "created": "준비",
        "recording": "녹음 중",
        "recorded": "녹음 완료",
        "transcribing": "전사 중",
        "transcribed": "전사 완료",
        "summarizing": "노트 생성 중",
        "completed": "완료",
        "failed": "실패",
    }.get(raw, raw or "-")


def fill_session_table(table: QTableWidget, rows: list[dict[str, Any]]) -> None:
    sorting_enabled = table.isSortingEnabled()
    header = table.horizontalHeader()
    sort_column = header.sortIndicatorSection()
    sort_order = header.sortIndicatorOrder()
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column, key in enumerate(("session_id", "date", "title", "course", "status")):
            value = format_status(row.get(key)) if key == "status" else str(row.get(key) or "")
            item = QTableWidgetItem(value)
            if column in (1, 4):
                item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row_index, column, item)
    table.setSortingEnabled(sorting_enabled)
    if sorting_enabled and sort_column >= 0:
        table.sortItems(sort_column, sort_order)


def main() -> None:
    application = QApplication(sys.argv)
    application.setApplicationName("Lecture Auto")
    application.setOrganizationName("Lecture Auto")
    icon_path = Path(__file__).resolve().parent / "assets" / "app-icon.png"
    if icon_path.exists():
        application.setWindowIcon(QIcon(str(icon_path)))
    application.setStyle("Fusion")
    application.setStyleSheet(APP_STYLE)
    repository = ConfigRepository()
    config = repository.load(load_secrets=False)
    smoke_test = os.environ.get("LECTURE_AUTO_SMOKE_TEST") == "1"
    if not repository.exists() and not smoke_test:
        onboarding = OnboardingDialog(config)
        if onboarding.exec() != QDialog.Accepted:
            return
        config = onboarding.apply(config)
        repository.save(config)
    window = MainWindow(repository, config)
    window.show()
    if smoke_test:
        QTimer.singleShot(1000, application.quit)
    raise SystemExit(application.exec())


if __name__ == "__main__":
    main()
