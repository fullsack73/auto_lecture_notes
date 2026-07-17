import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lecture_auto.library_service import LibraryService
from lecture_auto.session_metadata_store import SessionMetadataStore
from lecture_auto.session_service import SessionCommandError


@pytest.fixture
def workspace_with_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        (base_dir / "notes").mkdir()
        (base_dir / "transcripts").mkdir()
        (base_dir / "recordings").mkdir()
        (base_dir / "metadata").mkdir()

        metadata_file = base_dir / "metadata" / "sessions.json"
        store = SessionMetadataStore(metadata_file=metadata_file)
        yield base_dir, store


def _write_sessions(store: SessionMetadataStore, rows: list[dict]) -> None:
    store.metadata_file.parent.mkdir(parents=True, exist_ok=True)
    with store.metadata_file.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False)


def test_library_list_all_filters_together(workspace_with_store):
    base_dir, store = workspace_with_store
    _write_sessions(
        store,
        [
            {
                "session_id": "s-a",
                "date": "2026-03-01",
                "title": "A",
                "course": "C",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {"created_at": "2026-03-01T10:00:00Z"},
                "naming_pending": False,
            },
            {
                "session_id": "s-b",
                "date": "2026-03-02",
                "title": "B",
                "course": "C",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {"created_at": "2026-03-02T10:00:00Z"},
                "naming_pending": False,
            },
            {
                "session_id": "s-c",
                "date": "2026-03-02",
                "title": "C",
                "course": "C",
                "status": "idle",
                "audio_file_path": None,
                "timestamps": {"created_at": "2026-03-02T09:00:00Z"},
                "naming_pending": False,
            },
        ],
    )

    service = LibraryService(store=store, base_dir=base_dir)
    result = service.library_list(
        from_date="2026-03-01",
        to_date="2026-03-02",
        status_filter="completed",
        sort_recent=True,
    )
    assert [row["session_id"] for row in result.payload["sessions"]] == ["s-b", "s-a"]


def test_library_search_without_note_file_matches_session_id(workspace_with_store):
    base_dir, store = workspace_with_store
    _write_sessions(
        store,
        [
            {
                "session_id": "physics-101",
                "date": "2026-03-01",
                "title": "P",
                "course": "PHY",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {"created_at": "2026-03-01T10:00:00Z"},
                "naming_pending": False,
            }
        ],
    )

    service = LibraryService(store=store, base_dir=base_dir)
    result = service.library_search("physics")
    assert len(result.payload["sessions"]) == 1
    assert result.payload["sessions"][0]["session_id"] == "physics-101"


def test_library_search_no_matches_returns_empty_payload(workspace_with_store):
    base_dir, store = workspace_with_store
    _write_sessions(
        store,
        [
            {
                "session_id": "chem-101",
                "date": "2026-03-01",
                "title": "Chem",
                "course": "CHEM",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {"created_at": "2026-03-01T10:00:00Z"},
                "naming_pending": False,
            }
        ],
    )

    service = LibraryService(store=store, base_dir=base_dir)
    result = service.library_search("biology")
    assert result.payload["sessions"] == []


def test_library_open_raises_for_unknown_session(workspace_with_store):
    base_dir, store = workspace_with_store
    _write_sessions(store, [])

    service = LibraryService(store=store, base_dir=base_dir)
    with pytest.raises(SessionCommandError):
        service.library_open("missing")


def test_library_open_returns_clear_message_for_missing_target_folder(workspace_with_store):
    base_dir, store = workspace_with_store
    _write_sessions(
        store,
        [
            {
                "session_id": "known",
                "date": "2026-03-01",
                "title": "Known",
                "course": "C",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {"created_at": "2026-03-01T10:00:00Z"},
                "naming_pending": False,
            }
        ],
    )
    (base_dir / "notes").rmdir()

    service = LibraryService(store=store, base_dir=base_dir)
    result = service.library_open("known")
    assert result.payload["exists"] is False
    assert "does not exist" in result.message


def test_library_open_transcript_and_recordings_flags(workspace_with_store):
    base_dir, store = workspace_with_store
    _write_sessions(
        store,
        [
            {
                "session_id": "known",
                "date": "2026-03-01",
                "title": "Known",
                "course": "C",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {"created_at": "2026-03-01T10:00:00Z"},
                "naming_pending": False,
            }
        ],
    )

    service = LibraryService(store=store, base_dir=base_dir)
    with patch("lecture_auto.library_service._open_folder") as open_mock:
        service.library_open("known", open_transcript=True)
        transcript_path = open_mock.call_args.args[0]
        service.library_open("known", open_recordings=True)
        recording_path = open_mock.call_args.args[0]

    assert "transcripts" in str(transcript_path)
    assert "recordings" in str(recording_path)


def test_sort_recent_orders_by_latest_timestamp(workspace_with_store):
    base_dir, store = workspace_with_store
    _write_sessions(
        store,
        [
            {
                "session_id": "older",
                "date": "2026-03-01",
                "title": "Old",
                "course": "C",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {
                    "created_at": "2026-03-01T10:00:00Z",
                    "updated_at": "2026-03-01T10:05:00Z",
                },
                "naming_pending": False,
            },
            {
                "session_id": "newer",
                "date": "2026-03-01",
                "title": "New",
                "course": "C",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {
                    "created_at": "2026-03-01T10:00:00Z",
                    "updated_at": "2026-03-01T10:10:00Z",
                },
                "naming_pending": False,
            },
        ],
    )

    service = LibraryService(store=store, base_dir=base_dir)
    result = service.library_list(sort_recent=True)
    assert [row["session_id"] for row in result.payload["sessions"]] == ["newer", "older"]


def test_sort_recent_ignores_non_timestamp_capture_metadata(workspace_with_store):
    base_dir, store = workspace_with_store
    _write_sessions(
        store,
        [
            {
                "session_id": "older-capture",
                "date": "2026-03-01",
                "title": "Old capture",
                "course": "C",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {
                    "created_at": "2026-03-01T10:00:00Z",
                    "recording_completed_at": "2026-03-01T11:00:00Z",
                    "capture_process_id": 31079,
                    "capture_backend": "ffmpeg",
                },
                "naming_pending": False,
            },
            {
                "session_id": "newer",
                "date": "2026-03-02",
                "title": "New",
                "course": "C",
                "status": "completed",
                "audio_file_path": None,
                "timestamps": {
                    "created_at": "2026-03-02T10:00:00Z",
                    "updated_at": "2026-03-02T11:00:00Z",
                },
                "naming_pending": False,
            },
        ],
    )

    service = LibraryService(store=store, base_dir=base_dir)

    listed = service.library_list(sort_recent=True)
    searched = service.library_search("", sort_recent=True)

    assert [row["session_id"] for row in listed.payload["sessions"]] == [
        "newer",
        "older-capture",
    ]
    assert [row["session_id"] for row in searched.payload["sessions"]] == [
        "newer",
        "older-capture",
    ]
