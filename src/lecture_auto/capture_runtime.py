from __future__ import annotations

import subprocess
import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


class CaptureRuntimeError(RuntimeError):
    """Base class for runtime capture errors."""


class CaptureDependencyError(CaptureRuntimeError):
    """Raised when runtime dependencies are missing."""


class CapturePermissionError(CaptureRuntimeError):
    """Raised when OS denies audio capture permission."""


class CaptureDeviceError(CaptureRuntimeError):
    """Raised when an audio device is unavailable."""


class CaptureInterruptedError(CaptureRuntimeError):
    """Raised when capture session is interrupted."""


@dataclass
class CaptureHandle:
    session_id: str
    output_path: str
    process_id: int
    backend: str


@dataclass(frozen=True)
class AudioDevice:
    id: str
    name: str
    source: Literal["microphone", "system_audio"]
    backend: str


class CaptureRuntimeAdapter(Protocol):
    def list_devices(self) -> list[AudioDevice]:
        ...

    def start_capture(self, session_id: str, output_path: str) -> CaptureHandle:
        ...

    def stop_capture(
        self,
        session_id: str,
        *,
        interrupted: bool = False,
        process_id: int | None = None,
    ) -> None:
        ...


class NoopCaptureRuntimeAdapter:
    """Deterministic runtime adapter used by default for non-device environments."""

    def __init__(self) -> None:
        self._next_pid = 1000
        self._active: dict[str, CaptureHandle] = {}

    def list_devices(self) -> list[AudioDevice]:
        return [AudioDevice(id="default", name="Default microphone", source="microphone", backend="noop")]

    def start_capture(self, session_id: str, output_path: str) -> CaptureHandle:
        if session_id in self._active:
            raise CaptureRuntimeError(f"Session '{session_id}' is already capturing")

        self._next_pid += 1
        handle = CaptureHandle(
            session_id=session_id,
            output_path=output_path,
            process_id=self._next_pid,
            backend="noop",
        )
        self._active[session_id] = handle
        return handle

    def stop_capture(
        self,
        session_id: str,
        *,
        interrupted: bool = False,
        process_id: int | None = None,
    ) -> None:
        if session_id not in self._active:
            raise CaptureRuntimeError(f"No active capture for session '{session_id}'")

        self._active.pop(session_id)


class FFmpegCaptureRuntimeAdapter:
    """Real runtime adapter that starts/stops FFmpeg-based audio capture."""

    def __init__(
        self,
        ffmpeg_bin: str | None = None,
        capture_source: str = "microphone",
        device_id: str | None = None,
        device_name: str | None = None,
        backend: str | None = None,
        platform: str | None = None,
    ) -> None:
        self.ffmpeg_bin = ffmpeg_bin or self._resolve_ffmpeg_bin()
        self.capture_source = capture_source
        self.device_id = device_id
        self.device_name = device_name
        self.platform = platform or sys.platform
        self.backend = backend or self._default_backend()
        self._processes: dict[str, subprocess.Popen[bytes]] = {}

    @staticmethod
    def _resolve_ffmpeg_bin() -> str:
        executable = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates = (
            bundle_root / "bin" / executable,
            Path(__file__).resolve().parent / "bin" / executable,
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return executable

    def _default_backend(self) -> str:
        if self.platform == "darwin":
            return "avfoundation"
        if self.platform == "win32":
            return "dshow"
        return "pulse"

    def list_devices(self) -> list[AudioDevice]:
        if self.backend == "avfoundation":
            return self._list_avfoundation_devices()
        if self.backend == "dshow":
            return self._list_dshow_devices()
        if self.backend == "pulse":
            devices = self._list_pulse_devices()
            return devices or self._list_alsa_devices()
        return self._list_alsa_devices()

    def _run_device_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except FileNotFoundError as exc:
            raise CaptureDependencyError(f"Required capture tool is unavailable: {command[0]}") from exc

    @staticmethod
    def _device_source(name: str, backend: str) -> Literal["microphone", "system_audio"]:
        lowered = name.lower()
        system_keywords = ("blackhole", "soundflower", "loopback", "stereo mix", "monitor", "what u hear", "steam streaming")
        return "system_audio" if any(keyword in lowered for keyword in system_keywords) else "microphone"

    def _list_avfoundation_devices(self) -> list[AudioDevice]:
        result = self._run_device_command(
            [self.ffmpeg_bin, "-f", "avfoundation", "-list_devices", "true", "-i", ""]
        )
        devices: list[AudioDevice] = []
        in_audio = False
        for line in result.stderr.splitlines():
            if "AVFoundation audio devices:" in line:
                in_audio = True
                continue
            if "AVFoundation video devices:" in line:
                in_audio = False
                continue
            if not in_audio:
                continue
            match = re.search(r"\[(\d+)\]\s+(.+)$", line)
            if match:
                device_id, name = match.groups()
                devices.append(AudioDevice(device_id, name.strip(), self._device_source(name, "avfoundation"), "avfoundation"))
        return devices

    def _list_dshow_devices(self) -> list[AudioDevice]:
        result = self._run_device_command(
            [self.ffmpeg_bin, "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
        )
        devices: list[AudioDevice] = []
        in_audio = False
        for line in result.stderr.splitlines():
            lowered = line.lower()
            if "directshow audio devices" in lowered:
                in_audio = True
                continue
            if "directshow video devices" in lowered:
                in_audio = False
                continue
            if not in_audio or "alternative name" in lowered:
                continue
            match = re.search(r'"([^"]+)"', line)
            if match:
                name = match.group(1)
                devices.append(AudioDevice(name, name, self._device_source(name, "dshow"), "dshow"))
        return devices

    def _list_pulse_devices(self) -> list[AudioDevice]:
        try:
            result = self._run_device_command(["pactl", "list", "short", "sources"])
        except CaptureDependencyError:
            return []
        devices: list[AudioDevice] = []
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) < 2:
                fields = line.split()
            if len(fields) >= 2:
                device_id = fields[1]
                devices.append(AudioDevice(device_id, device_id, self._device_source(device_id, "pulse"), "pulse"))
        return devices

    def _list_alsa_devices(self) -> list[AudioDevice]:
        try:
            result = self._run_device_command(["arecord", "-L"])
        except CaptureDependencyError:
            return []
        devices = []
        for line in result.stdout.splitlines():
            if line and not line[0].isspace():
                name = line.strip()
                devices.append(AudioDevice(name, name, "microphone", "alsa"))
        return devices

    def _resolve_device_index(self) -> str:
        """Runs ffmpeg to list AVFoundation devices and returns the appropriate device index."""
        # Note: on Linux/Windows, this approach will differ. For macOS:
        if self.device_id:
            return self.device_id
        devices = self.list_devices()
        if self.device_name:
            for device in devices:
                if device.name == self.device_name:
                    return device.id
        matching = [device for device in devices if device.source == self.capture_source]
        if matching:
            return matching[0].id
        if self.capture_source == "system_audio":
            raise CaptureDeviceError(
                "No system audio loopback device found. Install or enable a loopback/monitor source."
            )
        if devices:
            return devices[0].id
        raise CaptureDeviceError("No accessible audio input device was found.")

    def _build_capture_command(self, device_id: str, output_path: str) -> list[str]:
        if self.backend == "avfoundation":
            input_args = ["-f", "avfoundation", "-i", f":{device_id}"]
        elif self.backend == "dshow":
            input_args = ["-f", "dshow", "-i", f"audio={device_id}"]
        elif self.backend == "alsa":
            input_args = ["-f", "alsa", "-i", device_id]
        else:
            input_args = ["-f", "pulse", "-i", device_id]
        return [self.ffmpeg_bin, "-y", *input_args, output_path]

    def start_capture(self, session_id: str, output_path: str) -> CaptureHandle:
        if session_id in self._processes:
            raise CaptureRuntimeError(f"Session '{session_id}' is already capturing")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        device_idx = self._resolve_device_index()

        command = self._build_capture_command(device_idx, output_path)

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except PermissionError as exc:
            raise CapturePermissionError("OS permissions denied capture startup") from exc
        except OSError as exc:
            raise CaptureDeviceError("Unable to open system audio device") from exc

        self._processes[session_id] = process
        return CaptureHandle(
            session_id=session_id,
            output_path=output_path,
            process_id=process.pid,
            backend=self.backend,
        )

    def stop_capture(
        self,
        session_id: str,
        *,
        interrupted: bool = False,
        process_id: int | None = None,
    ) -> None:
        process = self._processes.pop(session_id, None)
        if process is None and process_id is not None:
            self._stop_by_pid(process_id=process_id, interrupted=interrupted)
            return
        if process is None:
            raise CaptureRuntimeError(f"No active capture for session '{session_id}'")

        if interrupted:
            process.kill()
            return

        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            raise CaptureRuntimeError("Capture process did not stop gracefully")

    def _stop_by_pid(self, *, process_id: int, interrupted: bool) -> None:
        try:
            sig = signal.SIGKILL if interrupted else signal.SIGTERM
            os.kill(process_id, sig)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise CapturePermissionError("OS permissions denied capture shutdown") from exc
        except OSError as exc:
            raise CaptureRuntimeError("Capture process stop failed") from exc

        if interrupted:
            return

        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(process_id, 0)
            except ProcessLookupError:
                return
            except OSError:
                return
            time.sleep(0.1)

        try:
            os.kill(process_id, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError as exc:
            raise CaptureRuntimeError("Capture process did not stop gracefully") from exc
