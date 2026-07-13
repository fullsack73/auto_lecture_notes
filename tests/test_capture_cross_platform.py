from __future__ import annotations

from unittest.mock import patch

from lecture_auto.capture_runtime import AudioDevice, FFmpegCaptureRuntimeAdapter


def test_platform_capture_commands() -> None:
    mac = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg", backend="avfoundation", platform="darwin")
    windows = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg", backend="dshow", platform="win32")
    linux = FFmpegCaptureRuntimeAdapter(ffmpeg_bin="ffmpeg", backend="pulse", platform="linux")

    assert mac._build_capture_command("2", "out.wav") == ["ffmpeg", "-y", "-f", "avfoundation", "-i", ":2", "out.wav"]
    assert windows._build_capture_command("Microphone", "out.wav") == ["ffmpeg", "-y", "-f", "dshow", "-i", "audio=Microphone", "out.wav"]
    assert linux._build_capture_command("source.monitor", "out.wav") == ["ffmpeg", "-y", "-f", "pulse", "-i", "source.monitor", "out.wav"]


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
