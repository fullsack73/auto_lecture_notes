from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from lecture_auto.capture_runtime import (
    AudioDevice,
    CaptureDeviceError,
    FFmpegCaptureRuntimeAdapter,
    resolve_bundled_media_tool,
)


def test_platform_capture_commands() -> None:
    mac = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg", backend="avfoundation", platform="darwin")
    windows = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg", backend="dshow", platform="win32")
    linux = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg", backend="pulse", platform="linux")

    for command in (
        mac._build_capture_command("2", "out.wav"),
        windows._build_capture_command("Microphone", "out.wav"),
        linux._build_capture_command("source.monitor", "out.wav"),
    ):
        assert "astats=metadata=1:reset=1" in command[-2]
        assert command[-1] == "out.wav"


def test_selected_device_is_used_without_enumeration() -> None:
    runtime = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg", device_id="chosen", backend="pulse", platform="linux")
    with patch.object(runtime, "list_devices", side_effect=AssertionError("must not enumerate")):
        assert runtime._resolve_device_index() == "chosen"


def test_system_audio_requires_matching_device() -> None:
    runtime = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg", capture_source="system_audio", backend="pulse", platform="linux")
    with patch.object(runtime, "list_devices", return_value=[AudioDevice("mic", "Microphone", "microphone", "pulse")]):
        try:
            runtime._resolve_device_index()
        except Exception as exc:
            assert "system audio" in str(exc).lower()
        else:
            raise AssertionError("Expected missing system-audio device error")


def test_media_tool_resolver_prefers_app_bundle(tmp_path, monkeypatch) -> None:
    suffix = ".exe" if sys.platform == "win32" else ""
    executable = tmp_path / f"LectureAuto{suffix}"
    executable.write_text("")
    bundled_ffmpeg = tmp_path / "bin" / f"ffmpeg{suffix}"
    bundled_ffmpeg.parent.mkdir()
    bundled_ffmpeg.write_text("")
    monkeypatch.setattr("lecture_auto.capture_runtime.sys.executable", str(executable))

    assert resolve_bundled_media_tool("ffmpeg") == str(bundled_ffmpeg)


def test_capture_start_keeps_ffmpeg_control_pipe(tmp_path) -> None:
    process = MagicMock(pid=7001)
    runtime = FFmpegCaptureRuntimeAdapter(
        ffmpeg_bin="ffmpeg",
        device_id="Microphone",
        backend="dshow",
        platform="win32",
    )

    with patch("lecture_auto.capture_runtime.subprocess.Popen", return_value=process) as popen_mock:
        runtime.start_capture("session", str(tmp_path / "recording.wav"))

    assert popen_mock.call_args.kwargs["stdin"] == subprocess.PIPE
    assert popen_mock.call_args.kwargs["stderr"] == subprocess.PIPE


def test_capture_level_parses_latest_ffmpeg_peak() -> None:
    runtime = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg")

    assert runtime._parse_peak_level(
        b"lavfi.astats.Overall.Peak_level=-18.063656\n"
    ) == pytest.approx(-18.063656)
    assert runtime._parse_peak_level("lavfi.astats.Overall.Peak_level=-inf") == -60.0


def test_capture_stop_asks_ffmpeg_to_finalize_output() -> None:
    process = MagicMock()
    process.poll.return_value = None
    process.returncode = 0
    runtime = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg")
    runtime._processes["session"] = process

    runtime.stop_capture("session")

    process.stdin.write.assert_called_once_with(b"q\n")
    process.stdin.flush.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=5)
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_capture_stop_reports_early_ffmpeg_failure() -> None:
    process = MagicMock()
    process.poll.return_value = 1
    process.returncode = 1
    runtime = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg")
    runtime._processes["session"] = process

    with pytest.raises(CaptureDeviceError, match="exited before recording completed"):
        runtime.stop_capture("session")
