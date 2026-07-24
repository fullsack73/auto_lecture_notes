"""
Interactive TUI for lecture-auto.

Launched automatically when `lecture-auto` is run with no subcommand.
Uses questionary for arrow-key / enter navigation.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import questionary
import typer

from lecture_auto.cli_output import format_command_error, format_command_output
from lecture_auto.library_service import LibraryService
from lecture_auto.llm_config import DEFAULT_GEMINI_MODEL, normalize_gemini_model_name
from lecture_auto.session_service import SessionCommandError
from lecture_auto.stt_config import (
    LOCAL_MODEL_RECOMMENDATIONS,
    LOCAL_STT_HARDWARE_GUIDE,
    SUPPORTED_COMPUTE_TYPES,
    SUPPORTED_LOCAL_DEVICES,
)

# ── Styling ────────────────────────────────────────────────────────────────────
STYLE = questionary.Style(
    [
        ("qmark", "fg:#00bcd4 bold"),
        ("question", "bold"),
        ("answer", "fg:#00bcd4 bold"),
        ("pointer", "fg:#00bcd4 bold"),
        ("highlighted", "fg:#00bcd4 bold"),
        ("selected", "fg:#00bcd4"),
        ("separator", "fg:#6c757d"),
        ("instruction", "fg:#6c757d"),
        ("text", ""),
        ("disabled", "fg:#6c757d italic"),
    ]
)

SEPARATOR = questionary.Separator("─" * 40)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _echo_result(result) -> None:
    typer.echo(format_command_output(result, as_json=False))


def _echo_error(command: str, exc: SessionCommandError) -> None:
    typer.echo(format_command_error(command, exc, as_json=False))


def _ask(message: str, default: object = "") -> str | None:
    """Single-line text prompt. Returns None if user cancels (Ctrl+C)."""
    normalized_default = "" if default is None else str(default)
    return questionary.text(message, default=normalized_default, style=STYLE).ask()


def _select(message: str, choices: list) -> str | None:
    """Arrow-key selection. Returns None if user cancels."""
    return questionary.select(message, choices=choices, style=STYLE).ask()


def _select_stt_provider(current: str = "") -> str | None:
    """Select an STT API provider for persisted config."""
    choices = [
        questionary.Choice(
            title="OpenAI-compatible",
            value="openai-compatible",
            checked=current == "openai-compatible",
        ),
        questionary.Choice(
            title="Deepgram",
            value="deepgram",
            checked=current == "deepgram",
        ),
        questionary.Separator(),
        questionary.Choice(title="Clear value", value="__clear__"),
        questionary.Choice(title="Cancel", value="__cancel__"),
    ]
    return _select("Select STT API provider", choices)


def _select_stt_mode(current: str = "") -> str | None:
    """Select STT mode for persisted config."""
    choices = [
        questionary.Choice(
            title="API provider",
            value="api",
            checked=current == "api",
        ),
        questionary.Choice(
            title="Local Whisper model",
            value="local",
            checked=current == "local",
        ),
        questionary.Separator(),
        questionary.Choice(title="Clear value", value="__clear__"),
        questionary.Choice(title="Cancel", value="__cancel__"),
    ]
    return _select("Select STT mode", choices)


def _select_capture_source(current: str = "") -> str | None:
    """Select audio capture source for persisted config."""
    choices = [
        questionary.Choice(
            title="Microphone (default)",
            value="microphone",
            checked=current == "microphone" or current == "",
        ),
        questionary.Choice(
            title="System Audio (requires BlackHole, Loopback, etc.)",
            value="system_audio",
            checked=current == "system_audio",
        ),
        questionary.Separator(),
        questionary.Choice(title="Cancel", value="__cancel__"),
    ]
    return _select("Select capture source", choices)


def _select_stt_local_model(current: str = "") -> str | None:
    """Select a recommended local Whisper model or enter one manually."""
    choices = [
        questionary.Choice(
            title=f"{name} — {recommendation}",
            value=name,
            checked=current == name,
        )
        for name, recommendation in LOCAL_MODEL_RECOMMENDATIONS
    ]
    choices.extend(
        [
            questionary.Separator(),
            questionary.Choice(title="Enter custom model name...", value="__manual__"),
            questionary.Choice(title="Clear value", value="__clear__"),
            questionary.Choice(title="Cancel", value="__cancel__"),
        ]
    )
    selection = _select(
        f"Select local Whisper model\n{LOCAL_STT_HARDWARE_GUIDE}",
        choices,
    )
    if selection != "__manual__":
        return selection
    manual = _ask("Custom local model name", default=current)
    return manual


def _select_llm_model(provider: str = "", current: str = "") -> str | None:
    """Select an LLM model for persisted config.
    If provider is 'local', allow manual input. Otherwise use Google API presets.
    """
    provider = (provider or "").strip().lower()
    if provider in {"local", "ollama"}:
        return _ask("LLM model name (e.g. llama3, mistral)", default=current)

    normalized_current = normalize_gemini_model_name(current)
    choices = [
        questionary.Choice(
            title="Gemini Flash-Lite (recommended stable)",
            value=DEFAULT_GEMINI_MODEL,
            checked=normalized_current == DEFAULT_GEMINI_MODEL,
        ),
        questionary.Choice(
            title="Gemini Flash (more capable, preview)",
            value="gemini-3-flash-preview",
            checked=normalized_current == "gemini-3-flash-preview",
        ),
        questionary.Choice(
            title="Gemini Pro (most capable, preview)",
            value="gemini-3.1-pro-preview",
            checked=normalized_current == "gemini-3.1-pro-preview",
        ),
        questionary.Choice(
            title="Gemma 4 26B (Google API)",
            value="gemma-4-26b-a4b-it",
            checked=normalized_current == "gemma-4-26b-a4b-it",
        ),
        questionary.Choice(
            title="Gemma 4 31B (Google API)",
            value="gemma-4-31b-it",
            checked=normalized_current == "gemma-4-31b-it",
        ),
        questionary.Separator(),
        questionary.Choice(title="Clear value", value="__clear__"),
        questionary.Choice(title="Cancel", value="__cancel__"),
    ]
    return _select("Select LLM model", choices)


def _select_llm_provider(current: str = "") -> str | None:
    """Select an LLM provider for persisted config."""
    normalized_current = (current or "").strip().lower()
    choices = [
        questionary.Choice(
            title="Google API",
            value="gemini",
            checked=normalized_current == "gemini" or normalized_current == "",
        ),
        questionary.Choice(
            title="Local (Ollama)",
            value="local",
            checked=normalized_current in {"local", "ollama"},
        ),
        questionary.Separator(),
        questionary.Choice(title="Clear value", value="__clear__"),
        questionary.Choice(title="Cancel", value="__cancel__"),
    ]
    return _select("Select LLM provider", choices)


def _select_llm_thinking_level(current: str = "") -> str | None:
    """Select LLM thinking level for persisted config."""
    choices = [
        questionary.Choice(
            title="Minimal (fastest)",
            value="minimal",
            checked=current == "minimal",
        ),
        questionary.Choice(
            title="Low (faster, good for simple tasks)",
            value="low",
            checked=current == "low",
        ),
        questionary.Choice(
            title="Medium (balanced)",
            value="medium",
            checked=current == "medium",
        ),
        questionary.Choice(
            title="High (most capable, slower)",
            value="high",
            checked=current == "high",
        ),
        questionary.Separator(),
        questionary.Choice(title="Clear value", value="__clear__"),
        questionary.Choice(title="Cancel", value="__cancel__"),
    ]
    return _select("Select LLM thinking level", choices)


def _select_session(service, prompt: str = "Select a session") -> str | None:
    """Show session list and let user pick one by title / id."""
    try:
        result = service.session_history()
    except SessionCommandError as exc:
        _echo_error("session history", exc)
        return None

    sessions = result.payload.get("sessions", [])
    if not sessions:
        typer.echo("No sessions found. Create a session first.")
        return None

    while True:
        courses: dict[str, list[dict]] = {}
        no_course: list[dict] = []

        for s in sessions:
            c = s.get("course")
            if c:
                if c not in courses:
                    courses[c] = []
                courses[c].append(s)
            else:
                no_course.append(s)

        choices = []
        for c in sorted(courses.keys()):
            count = len(courses[c])
            choices.append(questionary.Choice(title=f"📁 {c} ({count} sessions)", value=f"__course__:{c}"))

        if courses and no_course:
            choices.append(questionary.Separator())

        for s in no_course:
            label = f"[{s['date']}] {s['title'] or '(no title)'} ({s['session_id']}) — {s['status']}"
            choices.append(questionary.Choice(title=label, value=s["session_id"]))

        choices.append(questionary.Separator())
        choices.append(questionary.Choice(title="← Back", value="__back__"))

        choice = questionary.select(prompt, choices=choices, style=STYLE).ask()

        if choice in (None, "__back__"):
            return None

        if choice.startswith("__course__:"):
            selected_course = choice.split(":", 1)[1]
            course_sessions = courses[selected_course]
            
            course_choices = []
            for s in course_sessions:
                label = f"[{s['date']}] {s['title'] or '(no title)'} ({s['session_id']}) — {s['status']}"
                course_choices.append(questionary.Choice(title=label, value=s["session_id"]))
            
            course_choices.append(questionary.Separator())
            course_choices.append(questionary.Choice(title="← Back to folders", value="__back__"))
            
            course_choice = questionary.select(f"{prompt} [{selected_course}]", choices=course_choices, style=STYLE).ask()
            
            if course_choice == "__back__":
                continue
            if course_choice is None:
                return None
            return course_choice

        return choice


def _active_recording_session_id(service) -> str | None:
    """Return the currently recording session, if one exists."""
    result = service.session_history()
    for session in result.payload.get("sessions", []):
        if session.get("status") == "recording":
            return session["session_id"]
    return None


# ── Config helpers (mirrors cli.py logic without typer context) ─────────────

def _get_global_config_path() -> Path:
    return Path.home() / ".lecture_auto" / "config.json"


def _load_config() -> dict:
    from lecture_auto.application import ConfigRepository

    repository = ConfigRepository()
    data = repository._read_raw()
    for name in ("stt_api_key", "gemini_api_key"):
        value = repository.secret_store.get(name)
        if value:
            data[name] = value
    return data


def _save_config(data: dict) -> None:
    from lecture_auto.application import ConfigRepository

    repository = ConfigRepository()
    for name in ("stt_api_key", "gemini_api_key"):
        if name in data:
            repository.set_secret(name, data.pop(name) or None)
    path = repository.path
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── Sub-menus ──────────────────────────────────────────────────────────────────

def _menu_session(service) -> None:
    while True:
        choice = _select(
            "Session",
            [
                questionary.Choice("✚  Create new session", "create"),
                questionary.Choice("📋  View history", "history"),
                questionary.Choice("🔍  View session detail", "detail"),
                questionary.Choice("🗑  Delete session", "delete"),
                SEPARATOR,
                questionary.Choice("← Back", "__back__"),
            ],
        )

        if choice in (None, "__back__"):
            return

        if choice == "history":
            try:
                result = service.session_history()
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("session history", exc)

        elif choice == "detail":
            session_id = _select_session(service, "Select session to view / edit")
            if session_id is None:
                continue
            _menu_session_detail(service, session_id)

        elif choice == "delete":
            session_id = _select_session(service, "Select session to delete")
            if session_id is None:
                continue
            
            confirm = questionary.confirm(f"Are you sure you want to delete session '{session_id}'? This cannot be undone.", style=STYLE).ask()
            if not confirm:
                typer.echo("Deletion cancelled.")
                continue

            try:
                result = service.session_delete(session_id=session_id)
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("session delete", exc)

        elif choice == "create":
            session_id = _ask("Session ID (e.g. cs101-2026-03-09)")
            if not session_id:
                continue
            date = _ask("Date (YYYY-MM-DD)", default=time.strftime("%Y-%m-%d"))
            if not date:
                continue
            title = _ask("Title (optional)")
            course = _ask("Course (optional)")
            try:
                result = service.session_create(
                    session_id=session_id,
                    date=date,
                    title=title or None,
                    course=course or None,
                )
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("session create", exc)

        typer.echo()  # breathing room after each action


def _menu_session_detail(service, session_id: str) -> None:
    """Per-session sub-menu: view detail or edit metadata."""
    while True:
        choice = _select(
            f"Session: {session_id}",
            [
                questionary.Choice("📄  View detail", "view"),
                questionary.Choice("✏   Edit metadata", "edit"),
                questionary.Choice("�  Audio management", "audio_management"),
                questionary.Choice("�📤  Import material (PDF)", "import_material"),
                SEPARATOR,
                questionary.Choice("← Back", "__back__"),
            ],
        )

        if choice in (None, "__back__"):
            return

        if choice == "view":
            try:
                result = service.session_detail(session_id=session_id)
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("session detail", exc)

        elif choice == "edit":
            new_id = _edit_session_metadata(service, session_id)
            if new_id and new_id != session_id:
                # Session was renamed — update the local reference and continue
                session_id = new_id

        elif choice == "audio_management":
            _menu_audio_management(service, session_id)

        elif choice == "import_material":
            material_path = _ask("Path to PDF material file:", default="")
            if not material_path or not material_path.strip():
                typer.secho("Import cancelled.", fg=typer.colors.YELLOW)
            else:
                try:
                    result = service.import_material(
                        session_id=session_id,
                        material_path=material_path.strip(),
                    )
                    _echo_result(result)
                except SessionCommandError as exc:
                    _echo_error("import material", exc)

        typer.echo()


def _menu_audio_management(service, session_id: str) -> None:
    """Per-session sub-menu for audio management."""
    while True:
        choice = _select(
            f"Audio Management for {session_id}",
            [
                questionary.Choice("�  Noise control (deepfilternet)", "noise_control"),
                questionary.Choice("🔊  Volume control (refine recording)", "volume_control"),
                SEPARATOR,
                questionary.Choice("← Back", "__back__"),
            ],
        )

        if choice in (None, "__back__"):
            return

        if choice == "noise_control":
            try:
                result = service.refine_audio_noise(session_id=session_id)
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("audio management", exc)

        elif choice == "volume_control":
            try:
                result = service.refine_audio_volume(session_id=session_id)
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("audio management", exc)
            
        typer.echo()


def _edit_session_metadata(service, session_id: str) -> str:
    """Edit title/course/date/session_id for a session.

    Returns the (possibly new) session_id after saving.
    """
    EDIT_FIELDS = [
        ("new_session_id", "Session ID"),
        ("date",           "Date (YYYY-MM-DD)"),
        ("title",          "Title"),
        ("course",         "Course"),
    ]

    pending: dict = {}

    while True:
        # Always load fresh so we can show current-or-pending values
        try:
            current = service.session_detail(session_id=session_id).payload
        except SessionCommandError as exc:
            _echo_error("session detail", exc)
            return session_id

        choices = []
        for key, label in EDIT_FIELDS:
            if key == "new_session_id":
                raw = pending.get(key, current.get("session_id", ""))
            else:
                raw = pending.get(key, current.get(key) or "")
            display = f"[{raw}] {label}" if raw else f"[ ] {label}"
            choices.append(questionary.Choice(title=display, value=key))

        choices.append(SEPARATOR)
        choices.append(questionary.Choice(title="💾  Save changes", value="__save__"))
        choices.append(questionary.Choice(title="✖  Cancel", value="__cancel__"))

        selected = _select("Select a field to edit", choices)

        if selected is None or selected == "__cancel__":
            typer.echo("Edit cancelled.")
            return session_id

        if selected == "__save__":
            if not pending:
                typer.echo("No changes to save.")
                return session_id
            try:
                result = service.session_update_metadata(session_id=session_id, **pending)
                _echo_result(result)
                return result.payload["session_id"]
            except SessionCommandError as exc:
                _echo_error("session update", exc)
                return session_id

        # Ask for new value
        if selected == "new_session_id":
            current_val = pending.get("new_session_id", current.get("session_id", ""))
        else:
            current_val = pending.get(selected, current.get(selected) or "")

        new_val = _ask(EDIT_FIELDS[[k for k, _ in EDIT_FIELDS].index(selected)][1], default=current_val)
        pending[selected] = new_val  # empty string means clear (service normalises)


def _menu_capture(service) -> None:
    while True:
        choice = _select(
            "Capture",
            [
                questionary.Choice("▶  Start capture", "start"),
                questionary.Choice("■  Stop capture", "stop"),
                SEPARATOR,
                questionary.Choice("← Back", "__back__"),
            ],
        )

        if choice in (None, "__back__"):
            return

        if choice == "start":
            session_id = _select_session(service, "Select session to record")
            if session_id is None:
                continue
            try:
                result = service.capture_start(session_id=session_id)
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("capture start", exc)

        elif choice == "stop":
            try:
                session_id = _active_recording_session_id(service)
            except SessionCommandError as exc:
                _echo_error("session history", exc)
                continue

            if session_id:
                typer.echo(f"Stopping active capture for session '{session_id}'.")
            else:
                session_id = _select_session(service, "Select session to stop")
            if session_id is None:
                continue
            try:
                result = service.capture_stop(session_id=session_id, success=True)
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("capture stop", exc)

        typer.echo()


def _menu_transcription(service) -> None:
    while True:
        choice = _select(
            "Transcription",
            [
                questionary.Choice("📝  Run transcription", "run"),
                questionary.Choice("✨  Refine transcript", "refine"),
                SEPARATOR,
                questionary.Choice("← Back", "__back__"),
            ],
        )

        if choice in (None, "__back__"):
            return

        if choice == "run":
            session_id = _select_session(service, "Select session to transcribe")
            if session_id is None:
                continue
            typer.echo("Running transcription… (this may take a while)")
            try:
                result = service.transcribe_session(session_id=session_id)
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("transcription run", exc)
                
        elif choice == "refine":
            session_id = _select_session(service, "Select session to refine transcript")
            if session_id is None:
                continue
            typer.echo("Refining transcript… (this may take a while)")
            try:
                result = service.transcript_refine(session_reference=session_id)
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("transcript refine", exc)

        typer.echo()


def _menu_summarize(service) -> None:
    session_id = _select_session(service, "Select session to summarize")
    if session_id is None:
        return

    preview_choice = _select(
        "Save or preview?",
        [
            questionary.Choice("Save to file", False),
            questionary.Choice("Preview only (no save)", True),
        ],
    )
    if preview_choice is None:
        return

    typer.echo("Generating summary…")
    try:
        result = service.summarize_session(
            session_reference=session_id,
            template_name=None,
            preview=preview_choice,
        )
        _echo_result(result)
    except SessionCommandError as exc:
        _echo_error("summarize", exc)
    typer.echo()


def _build_library_service(service) -> LibraryService:
    """Build a LibraryService from the SessionService's store and workspace."""
    base_dir = service.store.metadata_file.parent.parent
    return LibraryService(store=service.store, base_dir=base_dir)


def _menu_library(service) -> None:
    lib = _build_library_service(service)
    while True:
        choice = _select(
            "Library",
            [
                questionary.Choice("📋  List sessions", "list"),
                questionary.Choice("🔍  Search", "search"),
                questionary.Choice("📂  Open session folder", "open"),
                SEPARATOR,
                questionary.Choice("← Back", "__back__"),
            ],
        )

        if choice in (None, "__back__"):
            return

        if choice == "list":
            # Optional filters
            from_date = _ask("From date (YYYY-MM-DD, leave blank to skip)")
            if from_date is None:
                continue
            to_date = _ask("To date (YYYY-MM-DD, leave blank to skip)")
            if to_date is None:
                continue

            status_choice = _select(
                "Filter by status?",
                [
                    questionary.Choice("All statuses", ""),
                    questionary.Choice("idle", "idle"),
                    questionary.Choice("recording", "recording"),
                    questionary.Choice("completed", "completed"),
                    questionary.Choice("failed", "failed"),
                    questionary.Separator(),
                    questionary.Choice("Cancel", "__cancel__"),
                ],
            )
            if status_choice in (None, "__cancel__"):
                continue

            sort_choice = _select(
                "Sort order?",
                [
                    questionary.Choice("Default (by date)", "False"),
                    questionary.Choice("Most recent activity first", "True"),
                ],
            )
            if sort_choice is None:
                continue

            try:
                result = lib.library_list(
                    from_date=from_date.strip() or None,
                    to_date=to_date.strip() or None,
                    status_filter=status_choice or None,
                    sort_recent=(sort_choice == "True"),
                )
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("library list", exc)

        elif choice == "search":
            query = _ask("Search query")
            if not query or not query.strip():
                typer.echo("Search query cannot be empty.")
                continue

            try:
                result = lib.library_search(query=query.strip())
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("library search", exc)

        elif choice == "open":
            session_id = _select_session(service, "Select session to open")
            if session_id is None:
                continue

            folder_choice = _select(
                "Which folder to open?",
                [
                    questionary.Choice("📝  Notes", "notes"),
                    questionary.Choice("📄  Transcripts", "transcripts"),
                    questionary.Choice("🎙  Recordings", "recordings"),
                    questionary.Separator(),
                    questionary.Choice("Cancel", "__cancel__"),
                ],
            )
            if folder_choice in (None, "__cancel__"):
                continue

            try:
                result = lib.library_open(
                    session_id=session_id,
                    open_transcript=(folder_choice == "transcripts"),
                    open_recordings=(folder_choice == "recordings"),
                )
                _echo_result(result)
            except SessionCommandError as exc:
                _echo_error("library open", exc)

        typer.echo()


def _menu_config() -> bool:
    """Config menu. Returns True if config was saved (service should be rebuilt)."""
    config_changed = False
    while True:
        choice = _select(
            "Config",
            [
                questionary.Choice("👁  Show current config", "show"),
                questionary.Choice("✏  Set values", "set"),
                SEPARATOR,
                questionary.Choice("← Back", "__back__"),
            ],
        )

        if choice in (None, "__back__"):
            return config_changed

        if choice == "show":
            data = _load_config()
            if data:
                typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                typer.echo("No global configuration found.")

        elif choice == "set":
            data = _load_config()
            updated = False
            selected_key = None

            # Grouped config fields: (key, label) tuples organised by section.
            # A plain string entry acts as a section header / separator.
            field_groups: list[tuple[str, str] | str] = [
                "── General ──",
                ("workspace", "Workspace directory"),
                ("audio_format", "Audio format (wav or mp3)"),
                ("capture_source", "Capture source (microphone or system_audio)"),
                ("use_dynaudnorm", "Use dynaudnorm filter (True or False)"),
                ("dynaudnorm_f", "dynaudnorm f parameter (10-8000)"),
                ("dynaudnorm_g", "dynaudnorm g parameter (odd 3-301)"),
                ("gain_db", "Additional volume gain in dB (-60.0 to 60.0)"),
                "── STT (Speech-to-Text) ──",
                ("stt_mode", "STT mode (api or local)"),
                ("stt_language", "STT language (e.g. ko)"),
                ("stt_api_provider", "STT API provider"),
                ("stt_local_model", "Local Whisper model (e.g. base, large-v3)"),
                LOCAL_STT_HARDWARE_GUIDE,
                ("stt_local_device", "Local device (auto, cpu, cuda)"),
                ("stt_compute_type", "Compute type (auto, int8, int8_float16, float16, float32)"),
                ("stt_batch_size", "Batch size (batch > 1 requires VAD)"),
                ("stt_beam_size", "Beam size"),
                ("stt_temperature", "Temperature"),
                ("stt_vad_filter", "Use VAD (True or False)"),
                ("stt_vad_min_silence_duration_ms", "VAD minimum silence (milliseconds)"),
                ("stt_condition_on_previous_text", "Condition on previous text (True or False)"),
                ("stt_word_timestamps", "Collect word timestamps (True or False)"),
                ("stt_hotwords", "Hotwords/glossary terms"),
                ("stt_cpu_threads", "CPU threads (0 = runtime default)"),
                ("stt_num_workers", "Whisper workers"),
                "── LLM (Large Language Model) ──",
                ("llm_language", "LLM language (e.g. korean)"),
                ("llm_provider", "LLM provider (Google API or local)"),
                ("llm_model_name", "LLM model"),
                ("llm_thinking_level", "LLM thinking level"),
                "── API Keys ──",
                ("stt_api_key", "STT API key"),
                ("gemini_api_key", "Google API key"),
            ]

            # Flat list for lookup — only the actual (key, label) tuples.
            fields = [item for item in field_groups if isinstance(item, tuple)]

            while True:
                choices: list[Any] = []
                for item in field_groups:
                    if isinstance(item, str):
                        # Section separator
                        choices.append(questionary.Separator(item))
                    else:
                        key, label = item
                        current = data.get(key, "")
                        if key in ("stt_api_key", "gemini_api_key") and current:
                            display = f"[{'*' * min(len(current), 8)}] {label}"
                        else:
                            display = f"[{current}] {label}" if current else f"[ ] {label}"
                        choices.append(questionary.Choice(title=display, value=key))
                choices.append(questionary.Separator("─" * 30))
                choices.append(questionary.Choice(title="💾  Save changes", value="__save__"))
                choices.append(questionary.Choice(title="✖  Cancel", value="__cancel__"))
                
                selected_key = _select("Select a field to edit or save", choices)
                
                if selected_key in (None, "__cancel__"):
                    typer.echo("Config changes cancelled.")
                    updated = False
                    break
                    
                if selected_key == "__save__":
                    break

                if selected_key == "stt_api_provider":
                    value = _select_stt_provider(data.get(selected_key, "") or "")
                    if value in (None, "__cancel__"):
                        continue
                    if value == "__clear__":
                        value = ""
                elif selected_key == "capture_source":
                    value = _select_capture_source(data.get(selected_key, "") or "")
                    if value in (None, "__cancel__"):
                        continue
                elif selected_key == "stt_mode":
                    value = _select_stt_mode(data.get(selected_key, "") or "")
                    if value in (None, "__cancel__"):
                        continue
                    if value == "__clear__":
                        value = ""
                elif selected_key == "stt_local_model":
                    value = _select_stt_local_model(data.get(selected_key, "") or "")
                    if value in (None, "__cancel__"):
                        continue
                    if value == "__clear__":
                        value = ""
                elif selected_key == "llm_model_name":
                    value = _select_llm_model(
                        provider=data.get("llm_provider", ""),
                        current=data.get(selected_key, "") or "",
                    )
                    if value in (None, "__cancel__"):
                        continue
                    if value == "__clear__":
                        value = ""
                elif selected_key == "llm_provider":
                    value = _select_llm_provider(data.get(selected_key, "") or "")
                    if value in (None, "__cancel__"):
                        continue
                    if value == "__clear__":
                        value = ""
                elif selected_key == "llm_thinking_level":
                    value = _select_llm_thinking_level(data.get(selected_key, "") or "")
                    if value in (None, "__cancel__"):
                        continue
                    if value == "__clear__":
                        value = ""
                else:
                    prompt = next(label for k, label in fields if k == selected_key)
                    value = _ask(
                        f"New value for {prompt} (leave blank to skip/clear)",
                        default=data.get(selected_key, ""),
                    )
                
                if value is None:  # Ctrl+C
                    break

                value = value.strip()
                if value:
                    if selected_key == "audio_format" and value not in ("wav", "mp3"):
                        typer.echo("Invalid audio format. Must be 'wav' or 'mp3'. Skipping.")
                        continue
                    if selected_key == "stt_mode" and value not in ("api", "local"):
                        typer.echo("Invalid STT mode. Must be 'api' or 'local'. Skipping.")
                        continue
                    if (
                        selected_key == "stt_local_device"
                        and value not in SUPPORTED_LOCAL_DEVICES
                    ):
                        typer.echo("Invalid STT device. Use auto, cpu, or cuda. Skipping.")
                        continue
                    if (
                        selected_key == "stt_compute_type"
                        and value not in SUPPORTED_COMPUTE_TYPES
                    ):
                        typer.echo("Invalid STT compute type. Skipping.")
                        continue
                    if selected_key == "llm_provider":
                        normalized_provider = value.lower()
                        google_aliases = {"gemini", "google", "google_api", "google-api", "google api"}
                        valid_providers = google_aliases | {"local", "ollama"}
                        if normalized_provider not in valid_providers:
                            typer.echo("Invalid LLM provider. Must be 'gemini'/'google api' or 'local'. Skipping.")
                            continue
                        if normalized_provider in google_aliases:
                            value = "gemini"
                        elif normalized_provider == "ollama":
                            value = "local"
                    if selected_key in {
                        "use_dynaudnorm",
                        "stt_vad_filter",
                        "stt_condition_on_previous_text",
                        "stt_word_timestamps",
                    }:
                        if value.lower() not in ("true", "false", "1", "0", "yes", "no"):
                            typer.echo(f"Invalid boolean for {selected_key}. Skipping.")
                            continue
                        data[selected_key] = value.lower() in ("true", "1", "yes")
                        updated = True
                        continue
                    if selected_key in {
                        "stt_batch_size",
                        "stt_beam_size",
                        "stt_vad_min_silence_duration_ms",
                        "stt_cpu_threads",
                        "stt_num_workers",
                    }:
                        try:
                            numeric_value_stt = int(value)
                            minimum = 0 if selected_key == "stt_cpu_threads" else 1
                            if numeric_value_stt < minimum:
                                raise ValueError()
                        except ValueError:
                            typer.echo(f"Invalid integer for {selected_key}. Skipping.")
                            continue
                        data[selected_key] = numeric_value_stt
                        updated = True
                        continue
                    if selected_key == "stt_temperature":
                        try:
                            data[selected_key] = float(value)
                        except ValueError:
                            typer.echo("Invalid STT temperature. Skipping.")
                            continue
                        updated = True
                        continue
                    if selected_key == "dynaudnorm_f":
                        try:
                            numeric_value_f = int(value)
                            if numeric_value_f < 10 or numeric_value_f > 8000:
                                raise ValueError()
                        except ValueError:
                            typer.echo("Invalid f parameter. Must be between 10 and 8000. Skipping.")
                            continue
                        data[selected_key] = numeric_value_f
                        updated = True
                        continue
                    if selected_key == "dynaudnorm_g":
                        try:
                            numeric_value_g = int(value)
                            if numeric_value_g < 3 or numeric_value_g > 301 or numeric_value_g % 2 == 0:
                                raise ValueError()
                        except ValueError:
                            typer.echo("Invalid g parameter. Must be an odd integer between 3 and 301. Skipping.")
                            continue
                        data[selected_key] = numeric_value_g
                        updated = True
                        continue
                    if selected_key == "gain_db":
                        try:
                            numeric_value_gain = float(value)
                            if numeric_value_gain < -60.0 or numeric_value_gain > 60.0:
                                raise ValueError()
                        except ValueError:
                            typer.echo("Invalid gain_db. Must be a number between -60.0 and 60.0. Skipping.")
                            continue
                        data[selected_key] = numeric_value_gain
                        updated = True
                        continue
                    if selected_key == "workspace":
                        value = str(Path(value).expanduser().resolve())
                    data[selected_key] = value
                    updated = True
                elif selected_key in data:
                    del data[selected_key]
                    updated = True

            if updated:
                _save_config(data)
                typer.echo("✓ Config saved.")
                config_changed = True
            elif selected_key == "__save__":
                typer.echo("No changes made.")

        typer.echo()


# ── Entry Point ────────────────────────────────────────────────────────────────

def run_tui(service, *, service_factory=None) -> None:
    """Launch the interactive TUI main loop.
    
    Args:
        service: Initial SessionService instance.
        service_factory: Optional callable that returns a fresh SessionService.
            Called after config changes to pick up new settings.
    """
    typer.echo("\n🎓  lecture-auto  — interactive mode  (Ctrl+C to exit)\n")

    while True:
        choice = _select(
            "What would you like to do?",
            [
                questionary.Choice("📁  Session", "session"),
                questionary.Choice("🎙  Capture", "capture"),
                questionary.Choice("📝  Transcription", "transcription"),
                questionary.Choice("✨  Summarize", "summarize"),
                questionary.Choice("📚  Library", "library"),
                questionary.Choice("⚙   Config", "config"),
                SEPARATOR,
                questionary.Choice("🚪  Exit", "exit"),
            ],
        )

        if choice in (None, "exit"):
            typer.echo("Bye! 👋")
            break

        typer.echo()

        try:
            if choice == "session":
                _menu_session(service)
            elif choice == "capture":
                _menu_capture(service)
            elif choice == "transcription":
                _menu_transcription(service)
            elif choice == "summarize":
                _menu_summarize(service)
            elif choice == "library":
                _menu_library(service)
            elif choice == "config":
                config_changed = _menu_config()
                if config_changed and service_factory:
                    service = service_factory()
                    typer.echo("🔄 Settings reloaded.")
        except (KeyboardInterrupt, EOFError):
            typer.echo("\nReturning to main menu…\n")
            continue
