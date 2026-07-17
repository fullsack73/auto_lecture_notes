import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lecture_auto.library_service import LibraryService, _open_folder
from lecture_auto.session_metadata_store import SessionMetadataStore
from lecture_auto.session_service import SessionCommandError


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "notes").mkdir()
        (workspace / "transcripts").mkdir()
        (workspace / "recordings").mkdir()
        (workspace / "metadata").mkdir()
        yield workspace


@pytest.fixture
def sample_sessions():
    return [
        {
            "session_id": "lecture-001",
            "date": "2026-03-01",
            "title": "Introduction",
            "course": "CS101",
            "status": "completed",
            "audio_file_path": "recordings/lecture-001.wav",
            "timestamps": {
                "created_at": "2026-03-01T10:00:00Z",
                "modified_at": "2026-03-01T11:00:00Z",
            },
            "naming_pending": False,
        },
        {
            "session_id": "lecture-002",
            "date": "2026-03-05",
            "title": "Advanced Topics",
            "course": "CS101",
            "status": "idle",
            "audio_file_path": None,
            "timestamps": {"created_at": "2026-03-05T10:00:00Z"},
            "naming_pending": True,
        },
        {
            "session_id": "cs202-spring-2026",
            "date": "2026-02-20",
            "title": "Math Basics",
            "course": "MATH202",
            "status": "completed",
            "audio_file_path": "recordings/cs202-spring-2026.wav",
            "timestamps": {
                "created_at": "2026-02-20T14:00:00Z",
                "modified_at": "2026-02-20T15:30:00Z",
            },
            "naming_pending": False,
        },
    ]


@pytest.fixture
def library_service(temp_workspace, sample_sessions):
    metadata_file = temp_workspace / "metadata" / "sessions.json"
    store = SessionMetadataStore(metadata_file=metadata_file)
    with metadata_file.open("w", encoding="utf-8") as handle:
        json.dump(sample_sessions, handle, ensure_ascii=False)
    return LibraryService(store=store, base_dir=temp_workspace)


def test_library_list_returns_all_sessions(library_service, sample_sessions):
    result = library_service.library_list()
    assert result.command == "library list"
    assert len(result.payload["sessions"]) == len(sample_sessions)


def test_library_list_filters_and_sorts_recent(library_service):
    result = library_service.library_list(
        from_date="2026-03-01",
        to_date="2026-03-05",
        status_filter="completed",
        sort_recent=True,
    )
    assert [row["session_id"] for row in result.payload["sessions"]] == ["lecture-001"]


def test_library_search_matches_session_id(library_service):
    result = library_service.library_search("LECTURE")
    session_ids = {s["session_id"] for s in result.payload["sessions"]}
    assert session_ids == {"lecture-001", "lecture-002"}


def test_library_search_matches_note_content(library_service, temp_workspace):
    note_path = temp_workspace / "notes" / "lecture-001.md"
    note_path.write_text("This note mentions graph traversal.", encoding="utf-8")

    result = library_service.library_search("traversal")
    assert len(result.payload["sessions"]) == 1
    assert result.payload["sessions"][0]["session_id"] == "lecture-001"


def test_library_open_calls_platform_handler_for_existing_folder(library_service):
    with patch("lecture_auto.library_service._open_folder") as open_mock:
        result = library_service.library_open("lecture-001")

    assert result.command == "library open"
    assert result.payload["exists"] is True
    open_mock.assert_called_once()


def test_library_open_transcript_and_recordings_targets(library_service):
    with patch("lecture_auto.library_service._open_folder") as open_mock:
        library_service.library_open("lecture-001", open_transcript=True)
        transcript_path = open_mock.call_args.args[0]
        library_service.library_open("lecture-001", open_recordings=True)
        recording_path = open_mock.call_args.args[0]

    assert "transcripts" in str(transcript_path)
    assert "recordings" in str(recording_path)


def test_open_folder_uses_windows_shell_without_process_exit_code(tmp_path):
    with (
        patch("lecture_auto.library_service.sys.platform", "win32"),
        patch("lecture_auto.library_service.os.startfile", create=True) as startfile_mock,
    ):
        _open_folder(tmp_path)

    startfile_mock.assert_called_once_with(str(tmp_path))


def test_library_open_wraps_windows_shell_failure(library_service):
    with patch("lecture_auto.library_service._open_folder", side_effect=OSError("shell unavailable")):
        with pytest.raises(SessionCommandError) as exc_info:
            library_service.library_open("lecture-001")

    assert exc_info.value.code == "OPEN_FAILED"


def test_library_open_raises_on_unknown_session(library_service):
    with pytest.raises(SessionCommandError) as exc_info:
        library_service.library_open("missing-session")

    assert exc_info.value.code == "SESSION_NOT_FOUND"


def test_library_open_returns_message_when_folder_missing(library_service, temp_workspace):
    (temp_workspace / "notes").rmdir()

    result = library_service.library_open("lecture-001")
    assert result.payload["exists"] is False
    assert "does not exist" in result.message
