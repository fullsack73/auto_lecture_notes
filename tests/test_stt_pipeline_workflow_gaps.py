from pathlib import Path
import re

import pytest

from lecture_auto.session_metadata_store import SessionMetadataStore
from lecture_auto.session_service import SessionCommandError, SessionService
from lecture_auto.stt_config import STTConfig
from lecture_auto.stt_runtime import STTResult, STTTransientNetworkError


class TwoFailureAPIAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, *, audio_path: str) -> STTResult:
        self.calls += 1
        if self.calls <= 3:
            raise STTTransientNetworkError("temporary")
        return STTResult(transcript_text="ok", provider="fake", mode="api")


def _service(tmp_path: Path, adapter=None) -> SessionService:
    store = SessionMetadataStore(tmp_path / "config" / "sessions.json")
    return SessionService(
        store=store,
        stt_config=STTConfig(mode="api", api_provider="fake", api_key="k"),
        api_stt_adapter=adapter,
    )


def test_transcription_persists_latest_raw_transcript_for_same_session(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.session_create("session-1201", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1201", str(source))

    first = service.transcribe_session("session-1201")
    second = service.transcribe_session("session-1201")

    assert first.payload["transcript_file_path"] == "transcripts/session-1201-raw.md"
    assert second.payload["transcript_file_path"] == "transcripts/session-1201-raw.md"


def test_transcription_writes_raw_transcript_file_under_transcripts_folder(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.session_create("session-1202", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1202", str(source))

    service.transcribe_session("session-1202")

    transcript = tmp_path / "transcripts" / "session-1202-raw.md"
    assert transcript.exists()
    content = transcript.read_text(encoding="utf-8")
    expected_audio_path = str(
        (tmp_path / "recordings/session-1202-imported.wav").resolve()
    )
    assert f"transcript for {expected_audio_path}" in content
    assert not re.search(r"\[\d{2}:\d{2} - \d{2}:\d{2}\]", content)
    assert "\n" not in content.strip()


def test_api_transient_failures_stop_after_retry_cap_and_return_category_error(tmp_path: Path) -> None:
    adapter = TwoFailureAPIAdapter()
    service = _service(tmp_path, adapter=adapter)
    service.session_create("session-1203", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1203", str(source))

    with pytest.raises(SessionCommandError) as exc:
        service.transcribe_session("session-1203")

    assert exc.value.code == "TRANSCRIPTION_NETWORK_TRANSIENT_ERROR"
    assert adapter.calls == 3


def test_detail_includes_transcription_fields_after_success(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.session_create("session-1204", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1204", str(source))

    service.transcribe_session("session-1204")
    detail = service.session_detail("session-1204")

    assert detail.payload["transcription_status"] == "succeeded"
    assert detail.payload["transcript_file_path"] == "transcripts/session-1204-raw.md"
