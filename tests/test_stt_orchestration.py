from pathlib import Path
from unittest.mock import patch

import pytest

from lecture_auto.session_metadata_store import SessionMetadataStore
from lecture_auto.session_service import SessionCommandError, SessionService
from lecture_auto.stt_config import STTConfig
from lecture_auto.stt_runtime import (
    STTAudioDecodeError,
    STTProviderAuthError,
    STTResult,
    STTTransientNetworkError,
)


class FakeAPIAdapter:
    def __init__(self) -> None:
        self.calls = 0
        self.failures: list[Exception] = []

    def transcribe(self, *, audio_path: str) -> STTResult:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return STTResult(
            transcript_text=f"api transcript for {audio_path}",
            provider="fake-api",
            mode="api",
        )


class FakeLocalAdapter:
    def transcribe(self, *, audio_path: str) -> STTResult:
        return STTResult(
            transcript_text=f"local transcript for {audio_path}",
            provider="local",
            mode="local",
        )


def _service(tmp_path: Path, *, config: STTConfig, api_adapter=None, local_adapter=None) -> SessionService:
    store = SessionMetadataStore(tmp_path / "config" / "sessions.json")
    return SessionService(
        store=store,
        stt_config=config,
        api_stt_adapter=api_adapter,
        local_stt_adapter=local_adapter,
    )


def test_transcription_requires_session_linked_audio_and_rejects_external_source_path(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        config=STTConfig(mode="api", api_provider="fake", api_key="k"),
        api_adapter=FakeAPIAdapter(),
    )
    service.session_create("session-1001", "2026-03-06")

    with pytest.raises(SessionCommandError) as exc:
        service.transcribe_session("session-1001", source_audio_path="/tmp/external.wav")

    assert exc.value.code == "TRANSCRIPTION_SESSION_AUDIO_ONLY"


def test_api_mode_is_default_and_preflight_requires_key(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        config=STTConfig(),
        api_adapter=FakeAPIAdapter(),
    )
    service.session_create("session-1002", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1002", str(source))

    with pytest.raises(SessionCommandError) as exc:
        service.transcribe_session("session-1002")

    assert exc.value.code == "TRANSCRIPTION_CONFIG_ERROR"


def test_transient_api_failures_retry_up_to_two_times_then_succeed(tmp_path: Path) -> None:
    adapter = FakeAPIAdapter()
    adapter.failures = [STTTransientNetworkError("t1"), STTTransientNetworkError("t2")]
    service = _service(
        tmp_path,
        config=STTConfig(mode="api", api_provider="fake", api_key="k"),
        api_adapter=adapter,
    )
    service.session_create("session-1003", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1003", str(source))

    result = service.transcribe_session("session-1003")

    assert adapter.calls == 3
    assert result.payload["transcription_progress"]["retry_limit"] == 2
    assert result.payload["transcription_progress"]["attempt"] == 3
    assert result.payload["transcription_progress"]["final_status"] == "succeeded"


def test_local_mode_does_not_auto_retry_and_returns_actionable_error(tmp_path: Path) -> None:
    class FailingLocalAdapter:
        def __init__(self) -> None:
            self.calls = 0

        def transcribe(self, *, audio_path: str) -> STTResult:
            self.calls += 1
            raise STTAudioDecodeError("decode")

    local = FailingLocalAdapter()
    service = _service(
        tmp_path,
        config=STTConfig(mode="local", local_model_name="base"),
        local_adapter=local,
    )
    service.session_create("session-1004", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1004", str(source))

    with pytest.raises(SessionCommandError) as exc:
        service.transcribe_session("session-1004")

    assert local.calls == 1
    assert exc.value.code == "TRANSCRIPTION_AUDIO_DECODE_ERROR"


def test_provider_auth_error_maps_to_expected_category(tmp_path: Path) -> None:
    adapter = FakeAPIAdapter()
    adapter.failures = [STTProviderAuthError("bad key")]
    service = _service(
        tmp_path,
        config=STTConfig(mode="api", api_provider="fake", api_key="k"),
        api_adapter=adapter,
    )
    service.session_create("session-1005", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1005", str(source))

    with pytest.raises(SessionCommandError) as exc:
        service.transcribe_session("session-1005")

    assert exc.value.code == "TRANSCRIPTION_PROVIDER_AUTH_ERROR"


def test_deepgram_path_resolves_relative_audio_from_workspace(tmp_path: Path) -> None:
    class CapturingAdapter:
        def __init__(self) -> None:
            self.seen_audio_path: str | None = None

        def transcribe(self, *, audio_path: str) -> STTResult:
            self.seen_audio_path = audio_path
            return STTResult(
                transcript_text=f"api transcript for {audio_path}",
                provider="deepgram",
                mode="api",
            )

    adapter = CapturingAdapter()
    service = _service(
        tmp_path,
        config=STTConfig(mode="api", api_provider="deepgram", api_key="k"),
        api_adapter=adapter,
    )
    service.session_create("session-1006", "2026-03-06")

    workspace_audio = tmp_path / "recordings" / "session-1006.wav"
    workspace_audio.parent.mkdir(parents=True, exist_ok=True)
    workspace_audio.write_bytes(b"wav")
    session = service.session_detail("session-1006").payload
    session["audio_file_path"] = "recordings/session-1006.wav"
    service.store.upsert(session)

    result = service.transcribe_session("session-1006")

    assert result.payload["transcription_progress"]["final_status"] == "succeeded"
    assert adapter.seen_audio_path == str(workspace_audio.resolve())


def test_local_transcription_resolves_relative_audio_from_workspace(tmp_path: Path) -> None:
    class CapturingLocalAdapter:
        def __init__(self) -> None:
            self.seen_audio_path: str | None = None

        def transcribe(self, *, audio_path: str) -> STTResult:
            self.seen_audio_path = audio_path
            return STTResult(
                transcript_text="local transcript",
                provider="local",
                mode="local",
            )

    adapter = CapturingLocalAdapter()
    service = _service(
        tmp_path,
        config=STTConfig(mode="local", local_model_name="base"),
        local_adapter=adapter,
    )
    service.session_create("session-1006-local", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1006-local", str(source))

    service.transcribe_session("session-1006-local")

    expected = tmp_path / "recordings" / "session-1006-local-imported.wav"
    assert adapter.seen_audio_path == str(expected.resolve())


def test_audio_gain_default_is_noop_and_uses_original_path(tmp_path: Path) -> None:
    class CapturingAdapter:
        def __init__(self) -> None:
            self.seen_audio_path: str | None = None

        def transcribe(self, *, audio_path: str) -> STTResult:
            self.seen_audio_path = audio_path
            return STTResult(
                transcript_text=f"api transcript for {audio_path}",
                provider="fake-api",
                mode="api",
            )

    adapter = CapturingAdapter()
    service = _service(
        tmp_path,
        config=STTConfig(mode="api", api_provider="fake", api_key="k"),
        api_adapter=adapter,
    )
    service.session_create("session-1007", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1007", str(source))

    result = service.transcribe_session("session-1007")

    assert adapter.seen_audio_path == str(
        (tmp_path / "recordings/session-1007-imported.wav").resolve()
    )
    assert result.payload["transcription_progress"]["audio_amplification_applied"] is False
    assert result.payload["transcription_progress"]["use_dynaudnorm"] is False


def test_refine_audio_uses_amplified_temp_path_and_transcription_uses_it(tmp_path: Path) -> None:
    class CapturingAdapter:
        def __init__(self) -> None:
            self.seen_audio_path: str | None = None

        def transcribe(self, *, audio_path: str) -> STTResult:
            self.seen_audio_path = audio_path
            return STTResult(
                transcript_text=f"api transcript for {audio_path}",
                provider="fake-api",
                mode="api",
            )

    adapter = CapturingAdapter()
    service = _service(
        tmp_path,
        config=STTConfig(
            mode="api",
            api_provider="fake",
            api_key="k",
            use_dynaudnorm=True,
            dynaudnorm_f=100,
        ),
        api_adapter=adapter,
    )
    service.session_create("session-1008", "2026-03-06")
    source = tmp_path / "sample.wav"
    source.write_bytes(b"wav")
    service.import_audio("session-1008", str(source))

    # Write a dummy test file to fake the output of amplification.
    sample_amp_output = tmp_path / "amplified-input.wav"
    sample_amp_output.parent.mkdir(parents=True, exist_ok=True)
    sample_amp_output.write_bytes(b"refined wav")

    with patch("lecture_auto.session_service.amplified_audio_input") as amplifier:
        amplifier.return_value.__enter__.return_value = str(sample_amp_output)
        amplifier.return_value.__exit__.return_value = False

        refine_result = service.refine_audio_volume("session-1008")
        assert refine_result.command == "audio refine"

        result = service.transcribe_session("session-1008")

    assert adapter.seen_audio_path == str(
        (tmp_path / "recordings/session-1008-refined.wav").resolve()
    )
    assert result.payload["transcription_progress"]["audio_amplification_applied"] is True
    assert result.payload["transcription_progress"]["dynaudnorm_f"] == 100
