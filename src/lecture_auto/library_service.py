from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from lecture_auto.session_service import CommandResult, SessionCommandError
from lecture_auto.session_metadata_store import SessionMetadataStore


def _recent_activity_key(session: dict[str, Any]) -> str:
    """Return the latest actual timestamp while ignoring runtime metadata."""
    timestamps = session.get("timestamps", {})
    if not isinstance(timestamps, dict):
        return str(session.get("date") or "")

    activity_timestamps = (
        value
        for name, value in timestamps.items()
        if isinstance(name, str)
        and name.endswith("_at")
        and isinstance(value, str)
        and value
    )
    return max(activity_timestamps, default=str(session.get("date") or ""))


class LibraryService:
    """Service for managing and searching the library of lecture sessions."""

    def __init__(self, store: SessionMetadataStore, base_dir: Path) -> None:
        """
        Initialize LibraryService.

        Args:
            store: SessionMetadataStore for accessing session metadata
            base_dir: Base directory for notes, transcripts, and recordings folders
        """
        self.store = store
        self.base_dir = Path(base_dir)

    def library_list(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        status_filter: str | None = None,
        sort_recent: bool = False,
    ) -> CommandResult:
        """
        List all sessions from the store, optionally filtered and sorted.

        Args:
            from_date: ISO date string (YYYY-MM-DD), inclusive
            to_date: ISO date string (YYYY-MM-DD), inclusive
            status_filter: Filter by session status (e.g., "completed", "idle")
            sort_recent: If True, sort by most recent activity timestamp

        Returns:
            CommandResult with list of sessions
        """
        sessions = self.store.load_all()

        # Apply date range filter
        if from_date:
            sessions = [s for s in sessions if s["date"] >= from_date]
        if to_date:
            sessions = [s for s in sessions if s["date"] <= to_date]

        # Apply status filter
        if status_filter:
            sessions = [s for s in sessions if s["status"] == status_filter]

        # Apply sorting
        if sort_recent:
            sessions = sorted(
                sessions,
                key=_recent_activity_key,
                reverse=True,
            )

        return CommandResult(
            command="library list",
            payload={"sessions": sessions},
            message=f"Found {len(sessions)} session(s).",
        )

    def library_search(
        self,
        query: str,
        from_date: str | None = None,
        to_date: str | None = None,
        status_filter: str | None = None,
        sort_recent: bool = False,
    ) -> CommandResult:
        """
        Search sessions by session_id and note content (case-insensitive).

        Args:
            query: Search query string
            from_date: ISO date string (YYYY-MM-DD), inclusive
            to_date: ISO date string (YYYY-MM-DD), inclusive
            status_filter: Filter by session status
            sort_recent: If True, sort by most recent activity timestamp

        Returns:
            CommandResult with matching sessions
        """
        sessions = self.store.load_all()
        query_lower = query.lower()
        matched_sessions = []

        for session in sessions:
            # Match on session_id
            if query_lower in session["session_id"].lower():
                matched_sessions.append(session)
                continue

            # Match on note content if file exists
            note_relative = self.store.build_note_path(
                session["session_id"],
                course=session.get("course"),
            )
            note_path = self.base_dir / note_relative
            legacy_note_path = self.base_dir / "notes" / f"{session['session_id']}.md"
            candidate_paths = [note_path]
            if legacy_note_path != note_path:
                candidate_paths.append(legacy_note_path)

            for candidate in candidate_paths:
                if not candidate.exists():
                    continue
                try:
                    with candidate.open("r", encoding="utf-8") as f:
                        content = f.read()
                        if query_lower in content.lower():
                            matched_sessions.append(session)
                            break
                except (IOError, OSError):
                    pass

        # Apply date range filter
        if from_date:
            matched_sessions = [s for s in matched_sessions if s["date"] >= from_date]
        if to_date:
            matched_sessions = [s for s in matched_sessions if s["date"] <= to_date]

        # Apply status filter
        if status_filter:
            matched_sessions = [
                s for s in matched_sessions if s["status"] == status_filter
            ]

        # Apply sorting
        if sort_recent:
            matched_sessions = sorted(
                matched_sessions,
                key=_recent_activity_key,
                reverse=True,
            )

        return CommandResult(
            command="library search",
            payload={"sessions": matched_sessions},
            message=f"Found {len(matched_sessions)} matching session(s).",
        )

    def library_open(
        self,
        session_id: str,
        *,
        open_transcript: bool = False,
        open_recordings: bool = False,
    ) -> CommandResult:
        """
        Open a session's files in the OS file manager.

        Args:
            session_id: Session ID to open
            open_transcript: If True, open transcripts folder instead of notes
            open_recordings: If True, open recordings folder instead of notes

        Returns:
            CommandResult with opened folder path

        Raises:
            SessionCommandError: If session_id not found or folder does not exist
        """
        # Verify session exists
        session = self.store.get_by_session_id(session_id)
        if session is None:
            raise SessionCommandError(
                code="SESSION_NOT_FOUND",
                message=f"Session '{session_id}' not found.",
                guidance="Check that the session ID is correct.",
                exit_code=1,
            )

        # Determine target folder
        course = session.get("course")
        if open_transcript:
            transcript_rel = Path(
                self.store.build_raw_transcript_path(session_id, course=course)
            )
            target_folder = self.base_dir / transcript_rel.parent
            fallback_folder = self.base_dir / "transcripts"
        elif open_recordings:
            recording_rel = Path(
                self.store.build_recording_path(session_id, course=course)
            )
            target_folder = self.base_dir / recording_rel.parent
            fallback_folder = self.base_dir / "recordings"
        else:
            note_rel = Path(self.store.build_note_path(session_id, course=course))
            target_folder = self.base_dir / note_rel.parent
            fallback_folder = self.base_dir / "notes"

        if not target_folder.exists() and fallback_folder.exists():
            target_folder = fallback_folder

        # Check if folder exists
        if not target_folder.exists():
            return CommandResult(
                command="library open",
                payload={"opened_path": str(target_folder), "exists": False},
                message=f"Folder does not exist: {target_folder}",
            )

        # Open folder based on platform
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(target_folder)], check=True)
            elif sys.platform == "win32":
                subprocess.run(["explorer", str(target_folder)], check=True)
            else:  # Linux and other Unix-like systems
                subprocess.run(["xdg-open", str(target_folder)], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise SessionCommandError(
                code="OPEN_FAILED",
                message=f"Failed to open folder: {target_folder}",
                guidance="Check that the folder exists and the file manager is available.",
                exit_code=1,
            ) from e

        return CommandResult(
            command="library open",
            payload={"opened_path": str(target_folder), "exists": True},
            message=f"Opened: {target_folder}",
        )
