from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QDate, Qt, QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
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

from lecture_auto.application import AppConfig, ConfigRepository, ServiceContainer, build_service_container
from lecture_auto.capture_runtime import AudioDevice
from lecture_auto.gui.i18n import Translator
from lecture_auto.gui.jobs import JobController
from lecture_auto.llm_config import LLMConfig
from lecture_auto.local_runtime import RuntimeStatus
from lecture_auto.session_service import CommandResult, SessionCommandError
from lecture_auto.stt_config import STTConfig
from lecture_auto.tasking import TaskCancelledError, TaskEvent


APP_STYLE = """
QMainWindow { background: #f5f4ef; color: #20201d; }
QWidget { font-size: 13px; }
QFrame#Sidebar { background: #20211f; border: 0; }
QFrame#Sidebar QPushButton { color: #eeeeea; text-align: left; border: 0; padding: 12px 16px; }
QFrame#Sidebar QPushButton:hover, QFrame#Sidebar QPushButton:checked { background: #353732; }
QPushButton { padding: 7px 12px; border: 1px solid #b9b8b2; border-radius: 5px; background: #ffffff; }
QPushButton:hover { background: #ecebe5; }
QPushButton#Primary { background: #236b55; color: white; border-color: #236b55; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QPlainTextEdit { padding: 6px; background: white; border: 1px solid #c8c7c1; border-radius: 4px; }
QTableWidget, QListWidget, QTextBrowser { background: white; border: 1px solid #d4d2cc; border-radius: 5px; }
QHeaderView::section { background: #e8e7e1; padding: 7px; border: 0; }
QLabel#PageTitle { font-size: 24px; font-weight: 700; }
QLabel#Muted { color: #6c6b66; }
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


class HomePage(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        title = QLabel("Lecture Auto")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel("녹음부터 구조화 노트까지 한곳에서 처리")
        subtitle.setObjectName("Muted")
        layout.addWidget(subtitle)
        actions = QHBoxLayout()
        create = QPushButton("새 세션")
        create.setObjectName("Primary")
        create.clicked.connect(window.create_session)
        actions.addWidget(create)
        actions.addStretch()
        layout.addLayout(actions)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "날짜", "제목", "과목", "상태"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.doubleClicked.connect(self._open_selected)
        layout.addWidget(self.table)

    def refresh(self) -> None:
        sessions = self.window.container.session.session_history().payload["sessions"]
        self.summary.setText(f"전체 세션 {len(sessions)}개 · 실행 중 작업 {self.window.jobs.active_count}개")
        fill_session_table(self.table, sessions[:10])

    def _open_selected(self) -> None:
        item = self.table.item(self.table.currentRow(), 0)
        if item:
            self.window.sessions_page.select_session(item.text())
            self.window.show_page(1)


class SessionsPage(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self.current_session_id: str | None = None
        outer = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("세션")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()
        create = QPushButton("새 세션")
        create.setObjectName("Primary")
        create.clicked.connect(window.create_session)
        header.addWidget(create)
        outer.addLayout(header)
        self.search = QLineEdit()
        self.search.setPlaceholderText("ID, 제목, 과목 검색")
        self.search.textChanged.connect(self.refresh)
        outer.addWidget(self.search)
        content = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(260)
        self.list.currentItemChanged.connect(self._selection_changed)
        content.addWidget(self.list, 1)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.detail_title = QLabel("세션을 선택하세요")
        self.detail_title.setObjectName("PageTitle")
        self.detail_meta = QLabel()
        self.detail_meta.setWordWrap(True)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_meta)
        actions = QGridLayout()
        definitions = [
            ("수정", self.edit_session), ("삭제", self.delete_session),
            ("녹음 시작", self.capture_start), ("녹음 중지", self.capture_stop),
            ("오디오 가져오기", self.import_audio), ("자료 첨부", self.import_material),
            ("볼륨 보정", self.refine_volume), ("노이즈 제거", self.refine_noise),
            ("전사", self.transcribe), ("전사문 refine", self.refine_transcript),
            ("노트 미리보기", self.preview_notes), ("노트 저장", self.save_notes),
            ("노트 폴더", lambda: self.open_folder("notes")),
            ("전사문 폴더", lambda: self.open_folder("transcripts")),
            ("녹음 폴더", lambda: self.open_folder("recordings")),
        ]
        self.action_buttons: list[QPushButton] = []
        for index, (label, callback) in enumerate(definitions):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button, index // 4, index % 4)
            self.action_buttons.append(button)
        detail_layout.addLayout(actions)
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
            text = f"{row['date']}  {row.get('title') or row['session_id']}\n{row.get('course') or '과목 없음'} · {row['status']}"
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
            self.detail_meta.clear()
            self.raw_view.clear()
            self.transcript_view.clear()
            self.note_view.clear()
            return
        session = self.window.container.session.session_detail(session_id).payload
        self.detail_title.setText(str(session.get("title") or session_id))
        self.detail_meta.setText(f"{session['date']} · {session.get('course') or '과목 없음'} · {session['status']}")
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
        if self.window.config.stt.mode == "local" and not self.window.ensure_local_feature("whisper"):
            return
        self.window.run_background("전사", sid, lambda token, progress, job: self.window.container.session.transcribe_session(sid, cancellation_token=token, progress_callback=progress, job_id=job))

    def refine_transcript(self) -> None:
        sid = self._require_id()
        self.window.run_background("전사문 refine", sid, lambda token, progress, job: self.window.container.session.transcript_refine(sid, cancellation_token=token, progress_callback=progress, job_id=job))

    def preview_notes(self) -> None:
        sid = self._require_id()
        self.window.run_background("노트 미리보기", sid, lambda token, progress, job: self.window.container.session.summarize_session(sid, preview=True, cancellation_token=token, progress_callback=progress, job_id=job))

    def save_notes(self) -> None:
        sid = self._require_id()
        self.window.run_background("노트 저장", sid, lambda token, progress, job: self.window.container.session.summarize_session(sid, preview=False, cancellation_token=token, progress_callback=progress, job_id=job))

    def open_folder(self, kind: str) -> None:
        sid = self._require_id()
        self.window.execute(lambda: self.window.container.library.library_open(sid, open_transcript=kind == "transcripts", open_recordings=kind == "recordings"), refresh=False)


class LibraryPage(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        title = QLabel("보관함")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("세션 ID 또는 노트 내용 검색")
        button = QPushButton("검색")
        button.clicked.connect(self.refresh)
        row.addWidget(self.query)
        row.addWidget(button)
        layout.addLayout(row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "날짜", "제목", "과목", "상태"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        open_row = QHBoxLayout()
        for label, kind in (("노트 폴더", "notes"), ("전사문 폴더", "transcripts"), ("녹음 폴더", "recordings")):
            action = QPushButton(label)
            action.clicked.connect(lambda _checked=False, value=kind: self.open_selected(value))
            open_row.addWidget(action)
        open_row.addStretch()
        layout.addLayout(open_row)

    def refresh(self) -> None:
        query = self.query.text().strip()
        result = self.window.container.library.library_search(query) if query else self.window.container.library.library_list(sort_recent=True)
        fill_session_table(self.table, result.payload["sessions"])

    def open_selected(self, kind: str) -> None:
        item = self.table.item(self.table.currentRow(), 0)
        if not item:
            return
        self.window.execute(lambda: self.window.container.library.library_open(item.text(), open_transcript=kind == "transcripts", open_recordings=kind == "recordings"), refresh=False)


class SettingsPage(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self._runtime_probe_requested = False
        outer = QVBoxLayout(self)
        title = QLabel("설정")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
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
        self.devices = QComboBox()
        device_row = QHBoxLayout()
        device_row.addWidget(self.devices)
        device_refresh = QPushButton("장치 새로고침")
        device_refresh.clicked.connect(self.refresh_devices)
        device_row.addWidget(device_refresh)
        form.addRow("UI 언어", self.language)
        form.addRow("오디오 형식", self.audio_format)
        form.addRow("녹음 소스", self.capture_source)
        form.addRow("녹음 장치", device_row)
        self.stt_mode = combo((("API", "api"), ("로컬 Whisper", "local")))
        self.stt_provider = combo((("OpenAI-compatible", "openai-compatible"), ("Deepgram", "deepgram")))
        self.stt_key = QLineEdit()
        self.stt_key.setEchoMode(QLineEdit.Password)
        self.stt_model = combo(tuple((name, name) for name in ("base", "small", "medium", "large-v3")))
        self.stt_language = QLineEdit()
        self.dynaudnorm = QCheckBox()
        self.dynaudnorm_f = QSpinBox(); self.dynaudnorm_f.setRange(10, 8000)
        self.dynaudnorm_g = QSpinBox(); self.dynaudnorm_g.setRange(3, 301); self.dynaudnorm_g.setSingleStep(2)
        self.gain_db = QDoubleSpinBox(); self.gain_db.setRange(-60.0, 60.0); self.gain_db.setDecimals(1)
        form.addRow("STT 방식", self.stt_mode)
        form.addRow("STT API provider", self.stt_provider)
        form.addRow("STT API key", self.stt_key)
        form.addRow("Whisper 모델", self.stt_model)
        form.addRow("STT 언어", self.stt_language)
        form.addRow("dynaudnorm", self.dynaudnorm)
        form.addRow("dynaudnorm f", self.dynaudnorm_f)
        form.addRow("dynaudnorm g", self.dynaudnorm_g)
        form.addRow("추가 gain (dB)", self.gain_db)
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
        local_ai_header = QLabel("로컬 AI")
        local_ai_header.setStyleSheet("font-size: 17px; font-weight: 700; margin-top: 16px;")
        form.addRow(local_ai_header)
        self.runtime_python_status = QLabel("확인 전")
        self.runtime_whisper_status = QLabel("확인 전")
        self.runtime_deepfilter_status = QLabel("확인 전")
        self.runtime_path_status = QLabel("-")
        self.runtime_path_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.runtime_error_status = QLabel("-")
        self.runtime_error_status.setWordWrap(True)
        form.addRow("관리형 Python", self.runtime_python_status)
        form.addRow("Whisper runtime", self.runtime_whisper_status)
        form.addRow("DeepFilterNet runtime", self.runtime_deepfilter_status)
        form.addRow("선택 runtime 경로", self.runtime_path_status)
        form.addRow("마지막 probe 오류", self.runtime_error_status)
        runtime_actions = QGridLayout()
        runtime_buttons = (
            ("Whisper 설치", self.install_whisper_runtime),
            ("DeepFilterNet 설치", self.install_deepfilter_runtime),
            ("둘 다 설치", self.install_all_runtime),
            ("상태 다시 확인", self.probe_runtime),
            ("설치 복구", self.repair_runtime),
            ("runtime 제거", self.remove_runtime),
            ("외부 Python 선택", self.choose_external_python),
        )
        for index, (label, callback) in enumerate(runtime_buttons):
            button = QPushButton(label)
            button.clicked.connect(callback)
            runtime_actions.addWidget(button, index // 4, index % 4)
        form.addRow("Runtime 관리", runtime_actions)
        model_actions = QHBoxLayout()
        install = QPushButton("선택 Whisper 설치")
        install.clicked.connect(self.install_whisper)
        remove = QPushButton("선택 Whisper 삭제")
        remove.clicked.connect(self.delete_whisper)
        ollama = QPushButton("Ollama 상태/모델 확인")
        ollama.clicked.connect(self.check_ollama)
        pull = QPushButton("Ollama 모델 받기")
        pull.clicked.connect(self.pull_ollama)
        model_actions.addWidget(install); model_actions.addWidget(remove); model_actions.addWidget(ollama); model_actions.addWidget(pull)
        form.addRow("모델 관리", model_actions)
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
        self.refresh_devices()
        if not self._runtime_probe_requested:
            self._runtime_probe_requested = True
            QTimer.singleShot(0, self.probe_runtime)

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
            return manager.install_all(**kwargs)
        self.window.run_background(f"로컬 AI {feature} 설치", "__runtime__", work)

    def install_whisper_runtime(self) -> None:
        self._install_runtime("whisper")

    def install_deepfilter_runtime(self) -> None:
        self._install_runtime("deepfilter")

    def install_all_runtime(self) -> None:
        self._install_runtime("all")

    def probe_runtime(self) -> None:
        self.window.run_background("로컬 AI 상태 확인", None, lambda _token, _emit, _job: self.window.container.runtime.probe())

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
            self.workspace.setText(value)

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
        old = self.window.config
        device: AudioDevice | None = self.devices.currentData()
        config = AppConfig(
            workspace=Path(self.workspace.text()),
            ui_language=str(self.language.currentData()),
            audio_format=str(self.audio_format.currentData()),
            capture_source=str(self.capture_source.currentData()),
            capture_device_id=device.id if device else None,
            capture_device_name=device.name if device else None,
            capture_backend=device.backend if device else None,
            stt=STTConfig(
                mode=self.stt_mode.currentData(),
                api_provider=str(self.stt_provider.currentData()),
                api_key=self.stt_key.text().strip() or old.stt.api_key,
                local_model_name=str(self.stt_model.currentData()),
                language=self.stt_language.text().strip() or None,
                use_dynaudnorm=self.dynaudnorm.isChecked(),
                dynaudnorm_f=self.dynaudnorm_f.value(),
                dynaudnorm_g=self.dynaudnorm_g.value() | 1,
                gain_db=self.gain_db.value(),
            ),
            llm=LLMConfig(
                provider=str(self.llm_provider.currentData()),
                api_key=self.llm_key.text().strip() or old.llm.api_key,
                model_name=self.llm_model.text().strip(),
                thinking_level=str(self.thinking.currentData()),
                language=self.llm_language.text().strip() or None,
                ollama_base_url=self.ollama_url.text().strip() or "http://localhost:11434",
            ),
        )
        try:
            self.window.repository.save(config)
            self.window.reload_services(config)
            QMessageBox.information(self, "설정", "설정을 저장했습니다.")
        except Exception as exc:
            self.window.show_error(exc)

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
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(180)
        side_layout = QVBoxLayout(sidebar)
        brand = QLabel("LECTURE\nAUTO")
        brand.setStyleSheet("color: white; font-size: 20px; font-weight: 800; padding: 18px;")
        side_layout.addWidget(brand)
        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(("홈", "세션", "보관함", "설정")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=index: self.show_page(value))
            side_layout.addWidget(button)
            self.nav_buttons.append(button)
        side_layout.addStretch()
        root_layout.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(24, 20, 24, 16)
        self.stack = QStackedWidget()
        self.home_page = HomePage(self)
        self.sessions_page = SessionsPage(self)
        self.library_page = LibraryPage(self)
        self.settings_page = SettingsPage(self)
        for page in (self.home_page, self.sessions_page, self.library_page, self.settings_page):
            self.stack.addWidget(page)
        main.addWidget(self.stack, 1)
        task_header = QHBoxLayout()
        self.task_status = QLabel("준비됨")
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 1)
        self.task_progress.setValue(1)
        self.task_progress.setMaximumWidth(280)
        cancel = QPushButton("모든 작업 취소")
        cancel.clicked.connect(self.jobs.cancel_all)
        task_header.addWidget(self.task_status)
        task_header.addWidget(self.task_progress)
        task_header.addStretch()
        task_header.addWidget(cancel)
        main.addLayout(task_header)
        self.task_list = QListWidget()
        self.task_list.setMaximumHeight(90)
        main.addWidget(self.task_list)
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
                self.statusBar().showMessage(result.message, 5000)
            if refresh:
                self.refresh_all()
            return result
        except Exception as exc:
            self.show_error(exc)
            return None

    def run_background(self, label: str, session_id: str | None, work: Callable[..., Any]) -> None:
        try:
            job_id = self.jobs.submit(work, session_id=session_id)
            self._job_labels[job_id] = label
            item = QListWidgetItem(f"{label}: 대기 중")
            item.setData(Qt.UserRole, job_id)
            self.task_list.insertItem(0, item)
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
        if not count:
            self.task_progress.setRange(0, 1)
            self.task_progress.setValue(1)

    def show_error(self, exc: BaseException) -> None:
        if isinstance(exc, SessionCommandError):
            text = f"[{exc.code}] {exc.message}\n\n{exc.guidance}"
        else:
            text = str(exc)
        QMessageBox.critical(self, "오류", text)

    def reload_services(self, config: AppConfig) -> None:
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
        if (recording or self.jobs.active_count) and QMessageBox.question(self, "앱 종료", "녹음 또는 작업이 진행 중입니다. 종료할까요?") != QMessageBox.Yes:
            event.ignore()
            return
        self.jobs.cancel_all()
        event.accept()


def combo(items: tuple[tuple[str, str], ...]) -> QComboBox:
    widget = QComboBox()
    for label, value in items:
        widget.addItem(label, value)
    return widget


def set_combo(widget: QComboBox, value: object) -> None:
    index = widget.findData(value)
    if index >= 0:
        widget.setCurrentIndex(index)


def fill_session_table(table: QTableWidget, rows: list[dict[str, Any]]) -> None:
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column, key in enumerate(("session_id", "date", "title", "course", "status")):
            table.setItem(row_index, column, QTableWidgetItem(str(row.get(key) or "")))


def main() -> None:
    application = QApplication(sys.argv)
    application.setApplicationName("Lecture Auto")
    application.setOrganizationName("Lecture Auto")
    application.setStyleSheet(APP_STYLE)
    repository = ConfigRepository()
    config = repository.load()
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
