from __future__ import annotations

import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from lecture_auto.tasking import CancellationToken, TaskCancelledError


RuntimeFeature = Literal["whisper", "deepfilter"]
RuntimeProgress = Callable[[str, int | float | None, int | float | None, str], None]

WHISPER_PACKAGES = ("faster-whisper>=1.0.0",)
DEEPFILTER_PACKAGES = ("torch>=2.2.0", "torchaudio>=2.2.0", "deepfilternet>=0.5.6")


class LocalRuntimeError(RuntimeError):
    pass


class LocalRuntimeMissingError(LocalRuntimeError):
    def __init__(self, feature: RuntimeFeature) -> None:
        label = "Whisper" if feature == "whisper" else "DeepFilterNet"
        super().__init__(f"{label} runtime is not installed. Open Settings > Local AI to install it.")
        self.feature = feature


@dataclass(frozen=True)
class PackageStatus:
    found: bool = False
    import_ok: bool = False
    version: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RuntimeStatus:
    python_path: str | None = None
    python_version: str | None = None
    architecture: str | None = None
    source: str = "none"
    whisper_installed: bool = False
    whisper_version: str | None = None
    deepfilter_installed: bool = False
    deepfilter_version: str | None = None
    healthy: bool = False
    error: str | None = None
    packages: dict[str, PackageStatus] = field(default_factory=dict)

    def supports(self, feature: RuntimeFeature) -> bool:
        return self.whisper_installed if feature == "whisper" else self.deepfilter_installed


def default_runtime_dir() -> Path:
    override = os.environ.get("LECTURE_AUTO_RUNTIME_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Lecture Auto" / "runtime"
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return local / "Lecture Auto" / "runtime"
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "lecture-auto" / "runtime"


def _python_in_venv(root: Path) -> Path:
    return root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _normalized_arch(value: str | None) -> str:
    lowered = (value or "").lower()
    return {"amd64": "x86_64", "aarch64": "arm64"}.get(lowered, lowered)


class LocalRuntimeManager:
    _mutation_lock = threading.Lock()

    def __init__(
        self,
        runtime_dir: Path | None = None,
        *,
        external_python: str | None = None,
        uv_path: str | None = None,
        allow_development_python: bool = True,
        worker_script: Path | None = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir or default_runtime_dir())
        self.active_dir = self.runtime_dir / "active"
        self.python_install_dir = self.runtime_dir / "pythons"
        self.cache_dir = self.runtime_dir / "cache"
        self.state_file = self.runtime_dir / "runtime.json"
        self.mutation_file = self.runtime_dir / ".mutation.lock"
        self.external_python = external_python or self._load_external_python()
        self.uv_path = uv_path
        self.allow_development_python = allow_development_python
        self.worker_script = worker_script or self._resolve_worker_script()
        self.last_probe_error: str | None = None

    def _resolve_worker_script(self) -> Path:
        if "__compiled__" in globals():
            contents = Path(sys.executable).resolve().parent.parent
            for candidate in (
                contents / "MacOS" / "local_ai_worker.py",
                contents / "Resources" / "local_ai_worker.py",
            ):
                if candidate.exists():
                    return candidate
            return contents / "Resources" / "local_ai_worker.py"
        return Path(__file__).with_name("local_ai_worker.py")

    def _load_external_python(self) -> str | None:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            value = data.get("external_python")
            return str(value) if value else None
        except (OSError, json.JSONDecodeError, AttributeError):
            return None

    def set_external_python(self, executable: str | None) -> RuntimeStatus:
        if executable:
            status = self.probe_python(Path(executable), source="external")
            if not status.python_path or status.error:
                raise LocalRuntimeError(status.error or "External Python validation failed.")
            self.external_python = status.python_path
        else:
            self.external_python = None
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        temp = self.state_file.with_suffix(".tmp")
        temp.write_text(json.dumps({"external_python": self.external_python}, indent=2), encoding="utf-8")
        temp.replace(self.state_file)
        return self.probe()

    def candidate_pythons(self) -> list[tuple[str, Path]]:
        candidates: list[tuple[str, Path]] = []
        managed = _python_in_venv(self.active_dir)
        if managed.is_file():
            candidates.append(("managed", managed))
        if self.external_python:
            external = Path(self.external_python).expanduser()
            if external.is_file() and all(external != path for _, path in candidates):
                candidates.append(("external", external))
        if self.allow_development_python and "__compiled__" not in globals():
            current = Path(sys.executable).resolve()
            if all(current != path.resolve() for _, path in candidates):
                candidates.append(("development", current))
        return candidates

    def probe(self) -> RuntimeStatus:
        candidates = self.candidate_pythons()
        if not candidates:
            return RuntimeStatus(error="Local AI runtime is not installed.")
        first: RuntimeStatus | None = None
        errors: list[str] = []
        for source, python in candidates:
            status = self.probe_python(python, source=source)
            first = first or status
            if status.healthy:
                self.last_probe_error = None
                return status
            if status.error:
                errors.append(f"{source}: {status.error}")
            if status.whisper_installed or status.deepfilter_installed:
                self.last_probe_error = status.error
                return status
        error = "; ".join(errors) or "No candidate Python has a usable local AI runtime."
        self.last_probe_error = error
        return RuntimeStatus(
            python_path=first.python_path if first else None,
            python_version=first.python_version if first else None,
            architecture=first.architecture if first else None,
            source=first.source if first else "none",
            error=error,
            packages=first.packages if first else {},
        )

    def probe_python(self, python: Path, *, source: str) -> RuntimeStatus:
        if not python.is_file():
            return RuntimeStatus(source=source, error=f"Python executable not found: {python}")
        try:
            result = self._run_worker(python, {"action": "probe"}, timeout=90)
            architecture = str(result.get("architecture") or "")
            if _normalized_arch(architecture) != _normalized_arch(platform.machine()):
                return RuntimeStatus(
                    python_path=str(python),
                    python_version=result.get("python_version"),
                    architecture=architecture,
                    source=source,
                    error=f"Architecture mismatch: runtime={architecture}, app={platform.machine()}",
                )
            raw_packages = result.get("packages") or {}
            packages = {
                name: PackageStatus(
                    found=bool(value.get("found")),
                    import_ok=bool(value.get("import_ok")),
                    version=value.get("version"),
                    error=value.get("error"),
                )
                for name, value in raw_packages.items()
                if isinstance(value, dict)
            }
            whisper = all(packages.get(name, PackageStatus()).import_ok for name in ("faster_whisper", "ctranslate2"))
            deepfilter = all(packages.get(name, PackageStatus()).import_ok for name in ("torch", "torchaudio", "deepfilternet"))
            import_errors = [f"{name}: {value.error}" for name, value in packages.items() if value.found and not value.import_ok and value.error]
            return RuntimeStatus(
                python_path=str(result.get("python_path") or python),
                python_version=result.get("python_version"),
                architecture=architecture,
                source=source,
                whisper_installed=whisper,
                whisper_version=packages.get("faster_whisper", PackageStatus()).version,
                deepfilter_installed=deepfilter,
                deepfilter_version=packages.get("deepfilternet", PackageStatus()).version,
                healthy=whisper or deepfilter,
                error="; ".join(import_errors) or None,
                packages=packages,
            )
        except BaseException as exc:
            return RuntimeStatus(python_path=str(python), source=source, error=str(exc))

    def python_for(self, feature: RuntimeFeature) -> Path:
        errors: list[str] = []
        for source, python in self.candidate_pythons():
            status = self.probe_python(python, source=source)
            if status.supports(feature) and not status.error:
                return python
            if status.error:
                errors.append(status.error)
        self.last_probe_error = "; ".join(errors) or f"{feature} runtime is not installed."
        raise LocalRuntimeMissingError(feature)

    def install(
        self,
        features: set[RuntimeFeature],
        *,
        progress: RuntimeProgress | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> RuntimeStatus:
        if not features:
            raise ValueError("At least one runtime feature is required.")
        self._acquire_mutation()
        token = cancellation_token or CancellationToken()
        staging = self.runtime_dir / f".staging-{uuid.uuid4().hex}"
        backup = self.runtime_dir / f".backup-{uuid.uuid4().hex}"
        try:
            current = self.probe_python(_python_in_venv(self.active_dir), source="managed") if _python_in_venv(self.active_dir).is_file() else None
            requested = set(features)
            if current and current.whisper_installed:
                requested.add("whisper")
            if current and current.deepfilter_installed:
                requested.add("deepfilter")
            uv = self._resolve_uv()
            env = dict(os.environ)
            env["UV_PYTHON_INSTALL_DIR"] = str(self.python_install_dir)
            env["UV_CACHE_DIR"] = str(self.cache_dir)
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            self._step(progress, "python", 0, 4, "Preparing managed Python 3.11")
            token.raise_if_cancelled()
            self._run_command([str(uv), "python", "install", "3.11", "--install-dir", str(self.python_install_dir)], env, progress, token)
            self._step(progress, "venv", 1, 4, "Creating temporary runtime")
            self._run_command([str(uv), "venv", str(staging), "--python", "3.11", "--managed-python"], env, progress, token)
            packages: list[str] = []
            if "whisper" in requested:
                packages.extend(WHISPER_PACKAGES)
            if "deepfilter" in requested:
                packages.extend(DEEPFILTER_PACKAGES)
            self._step(progress, "packages", 2, 4, "Installing local AI packages")
            self._run_command([str(uv), "pip", "install", "--python", str(_python_in_venv(staging)), *packages], env, progress, token)
            token.raise_if_cancelled()
            self._step(progress, "probe", 3, 4, "Validating temporary runtime")
            status = self.probe_python(_python_in_venv(staging), source="managed")
            missing = [feature for feature in requested if not status.supports(feature)]
            if status.error or missing:
                raise LocalRuntimeError(status.error or f"Runtime validation failed for: {', '.join(missing)}")
            if self.active_dir.exists():
                self.active_dir.replace(backup)
            staging.replace(self.active_dir)
            shutil.rmtree(backup, ignore_errors=True)
            self._step(progress, "complete", 4, 4, "Local AI runtime installed")
            return self.probe_python(_python_in_venv(self.active_dir), source="managed")
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            if backup.exists() and not self.active_dir.exists():
                backup.replace(self.active_dir)
            raise
        finally:
            self._release_mutation()

    def install_whisper(self, **kwargs: Any) -> RuntimeStatus:
        return self.install({"whisper"}, **kwargs)

    def install_deepfilter(self, **kwargs: Any) -> RuntimeStatus:
        return self.install({"deepfilter"}, **kwargs)

    def install_all(self, **kwargs: Any) -> RuntimeStatus:
        return self.install({"whisper", "deepfilter"}, **kwargs)

    def repair(self, **kwargs: Any) -> RuntimeStatus:
        status = self.probe_python(_python_in_venv(self.active_dir), source="managed")
        features: set[RuntimeFeature] = set()
        if status.whisper_installed or any(name in status.packages for name in ("faster_whisper", "ctranslate2")):
            features.add("whisper")
        if status.deepfilter_installed or any(name in status.packages for name in ("torch", "torchaudio", "deepfilternet")):
            features.add("deepfilter")
        return self.install(features or {"whisper", "deepfilter"}, **kwargs)

    def remove(self) -> None:
        self._acquire_mutation()
        try:
            shutil.rmtree(self.active_dir, ignore_errors=True)
            for path in self.runtime_dir.glob(".staging-*"):
                shutil.rmtree(path, ignore_errors=True)
            for path in self.runtime_dir.glob(".backup-*"):
                shutil.rmtree(path, ignore_errors=True)
        finally:
            self._release_mutation()

    def _acquire_mutation(self) -> None:
        if not self._mutation_lock.acquire(blocking=False):
            raise LocalRuntimeError("Another local runtime mutation is already running.")
        try:
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            if self.mutation_file.exists():
                try:
                    pid = int(self.mutation_file.read_text(encoding="utf-8").strip())
                    os.kill(pid, 0)
                except (ValueError, OSError, ProcessLookupError):
                    self.mutation_file.unlink(missing_ok=True)
                else:
                    raise LocalRuntimeError("Another Lecture Auto process is modifying the local runtime.")
            descriptor = os.open(self.mutation_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
        except BaseException:
            self._mutation_lock.release()
            raise

    def _release_mutation(self) -> None:
        self.mutation_file.unlink(missing_ok=True)
        self._mutation_lock.release()

    def run_feature(
        self,
        feature: RuntimeFeature,
        request: dict[str, Any],
        *,
        progress: RuntimeProgress | None = None,
        cancellation_token: CancellationToken | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        python = self.python_for(feature)
        return self._run_worker(
            python,
            request,
            progress=progress,
            cancellation_token=cancellation_token,
            timeout=timeout,
        )

    def _resolve_uv(self) -> Path:
        candidates: list[Path] = []
        if self.uv_path:
            candidates.append(Path(self.uv_path))
        if "__compiled__" in globals():
            name = "uv.exe" if sys.platform == "win32" else "uv"
            contents = Path(sys.executable).resolve().parent.parent
            candidates.extend((
                contents / "MacOS" / "bin" / name,
                contents / "Resources" / "bin" / name,
            ))
        resolved = shutil.which("uv")
        if resolved:
            candidates.append(Path(resolved))
        candidates.append(Path(sys.executable).resolve().parent / ("uv.exe" if sys.platform == "win32" else "uv"))
        for candidate in candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        raise LocalRuntimeError("uv executable is unavailable. Reinstall Lecture Auto or configure LECTURE_AUTO_UV_PATH.")

    def _run_worker(
        self,
        python: Path,
        request: dict[str, Any],
        *,
        progress: RuntimeProgress | None = None,
        cancellation_token: CancellationToken | None = None,
        timeout: float | None = 600,
    ) -> dict[str, Any]:
        if not self.worker_script.is_file():
            raise LocalRuntimeError(f"Local AI worker script is missing: {self.worker_script}")
        token = cancellation_token or CancellationToken()
        process = subprocess.Popen(
            [str(python), str(self.worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        process.stdin.flush()
        process.stdin.close()
        events: queue.Queue[str | None] = queue.Queue()

        def reader() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                events.put(line)
            events.put(None)

        threading.Thread(target=reader, daemon=True).start()
        started = time.monotonic()
        result: dict[str, Any] | None = None
        worker_error: str | None = None
        while True:
            if token.is_cancelled:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise TaskCancelledError("Local AI worker was canceled.")
            if timeout is not None and time.monotonic() - started > timeout:
                process.kill()
                raise LocalRuntimeError("Local AI worker timed out.")
            try:
                line = events.get(timeout=0.1)
            except queue.Empty:
                if process.poll() is not None and events.empty():
                    break
                continue
            if line is None:
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            if event_type == "progress" and progress:
                progress(str(event.get("stage") or "working"), event.get("completed"), event.get("total"), str(event.get("message") or ""))
            elif event_type == "result":
                value = event.get("result")
                result = value if isinstance(value, dict) else {"value": value}
            elif event_type == "error":
                worker_error = str(event.get("message") or event.get("code") or "Worker failed")
        return_code = process.wait()
        if return_code != 0 or worker_error:
            stderr = process.stderr.read().strip() if process.stderr else ""
            raise LocalRuntimeError(worker_error or stderr[-2000:] or f"Local AI worker crashed with exit code {return_code}.")
        if result is None:
            raise LocalRuntimeError("Local AI worker exited without a result event.")
        return result

    @staticmethod
    def _step(progress: RuntimeProgress | None, stage: str, completed: int, total: int, message: str) -> None:
        if progress:
            progress(stage, completed, total, message)

    @staticmethod
    def _run_command(
        command: list[str],
        env: dict[str, str],
        progress: RuntimeProgress | None,
        token: CancellationToken,
    ) -> None:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, bufsize=1)
        assert process.stdout is not None
        log_tail: list[str] = []
        while True:
            line = process.stdout.readline()
            if line:
                stripped = line.strip()
                if stripped:
                    log_tail.append(stripped)
                    log_tail = log_tail[-20:]
                    if progress:
                        progress("installing", None, None, stripped[-300:])
            if token.is_cancelled:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise TaskCancelledError("Runtime installation was canceled.")
            if process.poll() is not None:
                break
            if not line:
                time.sleep(0.05)
        if process.returncode != 0:
            raise LocalRuntimeError("Runtime command failed:\n" + "\n".join(log_tail[-10:]))
