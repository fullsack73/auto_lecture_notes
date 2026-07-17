import subprocess
from unittest.mock import patch

import pytest

from lecture_auto.capture_runtime import FFmpegCaptureRuntimeAdapter, CaptureDeviceError


@pytest.fixture
def mock_ffmpeg_output():
    output = """Some FFmpeg banner text
[AVFoundation indev @ 0x1508046f0] AVFoundation video devices:
[AVFoundation indev @ 0x1508046f0] [0] FaceTime HD Camera
[AVFoundation indev @ 0x1508046f0] [1] Capture screen 0
[AVFoundation indev @ 0x1508046f0] AVFoundation audio devices:
[AVFoundation indev @ 0x1508046f0] [0] MacBook Air Microphone
[AVFoundation indev @ 0x1508046f0] [1] Steam Streaming Speakers
[AVFoundation indev @ 0x1508046f0] [2] Some Random Mic
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stderr = output
        yield mock_run


def test_resolve_device_index_system_audio(mock_ffmpeg_output) -> None:
    adapter = FFmpegCaptureRuntimeAdapter(capture_source="system_audio", backend="avfoundation", platform="darwin")
    idx = adapter._resolve_device_index()
    assert idx == "1"


def test_resolve_device_index_microphone(mock_ffmpeg_output) -> None:
    adapter = FFmpegCaptureRuntimeAdapter(capture_source="microphone", backend="avfoundation", platform="darwin")
    idx = adapter._resolve_device_index()
    assert idx == "0"


def test_resolve_device_index_system_audio_not_found() -> None:
    output = """[AVFoundation indev @ 0x100] AVFoundation audio devices:
[AVFoundation indev @ 0x100] [0] Just A Microphone
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stderr = output
        adapter = FFmpegCaptureRuntimeAdapter(capture_source="system_audio", backend="avfoundation", platform="darwin")
        with pytest.raises(CaptureDeviceError, match="No system audio loopback device found"):
            adapter._resolve_device_index()


def test_resolve_device_index_microphone_fallback() -> None:
    output = """[AVFoundation indev @ 0x100] AVFoundation audio devices:
[AVFoundation indev @ 0x100] [2] Weird Headset
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stderr = output
        adapter = FFmpegCaptureRuntimeAdapter(capture_source="microphone", backend="avfoundation", platform="darwin")
        idx = adapter._resolve_device_index()
        assert idx == "2"  # falls back to the first available if no explicit mic found
