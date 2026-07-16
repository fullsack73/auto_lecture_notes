from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import sys
from pathlib import Path

import pytest

import lecture_auto.local_runtime as local_runtime_module

from lecture_auto.local_runtime import (
    LocalRuntimeError,
    LocalRuntimeManager,
    RuntimeStatus,
)
from lecture_auto.tasking import CancellationToken, TaskCancelledError


def test_compiled_runtime_resolves_standalone_data_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = tmp_path / "LectureAuto.dist"
    executable = app / ("LectureAuto.exe" if sys.platform == "win32" else "LectureAuto")
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"app")
    worker = app / "local_ai_worker.py"
    gemini_worker = app / "gemini_addon_worker.py"
    uv = app / "bin" / ("uv.exe" if sys.platform == "win32" else "uv")
    worker.write_text("", encoding="utf-8")
    gemini_worker.write_text("", encoding="utf-8")
    make_executable(uv, "")
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(local_runtime_module, "__compiled__", object(), raising=False)

    manager = LocalRuntimeManager(tmp_path / "runtime")

    assert manager.worker_script == worker
    assert manager.gemini_worker_script == gemini_worker
    assert manager._resolve_uv() == uv


def make_executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def fake_probe_worker(tmp_path: Path, *, architecture: str | None = None) -> Path:
    architecture = architecture or ("arm64" if sys.platform == "darwin" else __import__("platform").machine())
    payload = {
        "python_path": sys.executable,
        "python_version": "3.11.9",
        "architecture": architecture,
        "packages": {
            "faster_whisper": {"found": True, "import_ok": True, "version": "1.2.0", "error": None},
            "ctranslate2": {"found": True, "import_ok": True, "version": "4.6.0", "error": None},
            "torch": {"found": True, "import_ok": True, "version": "2.7.0", "error": None},
            "torchaudio": {"found": True, "import_ok": True, "version": "2.7.0", "error": None},
            "deepfilternet": {"found": True, "import_ok": True, "version": "0.5.6", "error": None},
            "onnxruntime": {"found": False, "import_ok": False, "version": None, "error": None},
            "google_genai": {"found": True, "import_ok": True, "version": "1.66.0", "error": None},
        },
    }
    return make_executable(
        tmp_path / "worker.py",
        "import json,sys\n"
        "request=json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'type':'progress','stage':'probe','completed':1,'total':2,'message':'checking'}), flush=True)\n"
        f"print(json.dumps({{'type':'result','result':{payload!r}}}), flush=True)\n",
    )


def fake_uv(tmp_path: Path, *, fail_install: bool = False) -> Path:
    return make_executable(
        tmp_path / ("uv.py" if os.name == "nt" else "uv"),
        "#!/usr/bin/env python3\n"
        "import os,pathlib,subprocess,sys\n"
        "args=sys.argv[1:]\n"
        f"fail={fail_install!r}\n"
        "if args and args[0]=='venv':\n"
        " p=pathlib.Path(args[1]); subprocess.check_call([sys.executable,'-m','venv',str(p)])\n"
        "elif args[:2]==['pip','install'] and fail:\n"
        " print('simulated network failure'); raise SystemExit(3)\n"
        "print('ok')\n",
    )


def test_probe_parses_versions_and_external_python(tmp_path: Path) -> None:
    manager = LocalRuntimeManager(
        tmp_path / "runtime",
        external_python=sys.executable,
        worker_script=fake_probe_worker(tmp_path),
        allow_development_python=False,
    )

    status = manager.probe()

    assert status.source == "external"
    assert status.whisper_installed is True
    assert status.deepfilter_installed is True
    assert status.gemini_installed is True
    assert status.whisper_version == "1.2.0"


def test_architecture_mismatch_is_rejected(tmp_path: Path) -> None:
    current = {"amd64": "x86_64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    wrong = "arm64" if current == "x86_64" else "x86_64"
    manager = LocalRuntimeManager(
        tmp_path / "runtime",
        external_python=sys.executable,
        worker_script=fake_probe_worker(tmp_path, architecture=wrong),
        allow_development_python=False,
    )

    status = manager.probe()

    assert status.healthy is False
    assert "Architecture mismatch" in (status.error or "")


def test_worker_jsonl_progress_and_result(tmp_path: Path) -> None:
    events = []
    manager = LocalRuntimeManager(tmp_path / "runtime", worker_script=fake_probe_worker(tmp_path))

    result = manager._run_worker(
        Path(sys.executable),
        {"action": "probe"},
        progress=lambda *values: events.append(values),
    )

    assert result["python_version"] == "3.11.9"
    assert events[0][0] == "probe"


def test_worker_protocol_uses_utf8_for_korean_text(tmp_path: Path) -> None:
    worker = make_executable(
        tmp_path / "utf8_worker.py",
        "import json,sys\n"
        "request=json.loads(sys.stdin.readline())\n"
        "payload={'type':'result','result':{'message':request['message']}}\n"
        "sys.stdout.buffer.write((json.dumps(payload,ensure_ascii=False)+'\\n').encode('utf-8'))\n"
        "sys.stdout.buffer.flush()\n",
    )
    manager = LocalRuntimeManager(tmp_path / "runtime", worker_script=worker)

    result = manager._run_worker(Path(sys.executable), {"message": "강의 설치"})

    assert result["message"] == "강의 설치"


def test_runtime_command_decodes_utf8_progress_output(tmp_path: Path) -> None:
    command = make_executable(
        tmp_path / "utf8_output.py",
        "import sys\n"
        "sys.stdout.buffer.write('Whisper 설치 중\\n'.encode('utf-8'))\n"
        "sys.stdout.buffer.flush()\n",
    )
    progress_events: list[tuple[object, ...]] = []

    LocalRuntimeManager._run_command(
        [str(command)],
        dict(os.environ),
        lambda *values: progress_events.append(values),
        CancellationToken(),
    )

    assert progress_events[0][-1] == "Whisper 설치 중"


def test_windows_python_link_error_is_retried_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = LocalRuntimeManager(tmp_path / "runtime")
    calls: list[list[str]] = []
    progress_events: list[tuple[object, ...]] = []

    def run_command(
        command: list[str],
        env: dict[str, str],
        progress,
        token: CancellationToken,
    ) -> None:
        calls.append(command)
        if len(calls) == 1:
            raise LocalRuntimeError(
                "Runtime command failed:\n"
                "error: Failed to create Python minor version link directory\n"
                "Caused by: os error 448"
            )

    monkeypatch.setattr(local_runtime_module.sys, "platform", "win32")
    monkeypatch.setattr(manager, "_run_command", run_command)
    command = ["uv", "python", "install", "3.11"]

    manager._install_managed_python(
        command,
        {},
        lambda *values: progress_events.append(values),
        CancellationToken(),
    )

    assert calls == [command, command]
    assert progress_events[-1][-1] == "Retrying managed Python link creation"


def test_non_link_python_install_error_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = LocalRuntimeManager(tmp_path / "runtime")
    calls = 0

    def run_command(*args, **kwargs) -> None:
        nonlocal calls
        calls += 1
        raise LocalRuntimeError("Runtime command failed: network unavailable")

    monkeypatch.setattr(local_runtime_module.sys, "platform", "win32")
    monkeypatch.setattr(manager, "_run_command", run_command)

    with pytest.raises(LocalRuntimeError, match="network unavailable"):
        manager._install_managed_python(
            ["uv", "python", "install", "3.11"],
            {},
            None,
            CancellationToken(),
        )

    assert calls == 1


def test_worker_crash_is_isolated(tmp_path: Path) -> None:
    worker = make_executable(tmp_path / "crash.py", "import sys\nsys.stdin.readline()\nraise SystemExit(7)\n")
    manager = LocalRuntimeManager(tmp_path / "runtime", worker_script=worker)

    with pytest.raises(LocalRuntimeError, match="exit code 7"):
        manager._run_worker(Path(sys.executable), {"action": "probe"})


def test_fake_uv_install_atomically_activates_runtime(tmp_path: Path) -> None:
    manager = LocalRuntimeManager(
        tmp_path / "runtime",
        uv_path=str(fake_uv(tmp_path)),
        worker_script=fake_probe_worker(tmp_path),
        allow_development_python=False,
    )

    status = manager.install_whisper()

    assert status.whisper_installed
    active_python = manager.active_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert active_python.exists()
    assert not list(manager.runtime_dir.glob(".staging-*"))


def test_failed_install_preserves_existing_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    active_python = runtime / "active" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    active_python.parent.mkdir(parents=True)
    if os.name == "nt":
        shutil.copy2(sys.executable, active_python)
    else:
        active_python.symlink_to(sys.executable)
    marker = runtime / "active" / "keep.txt"
    marker.write_text("healthy", encoding="utf-8")
    manager = LocalRuntimeManager(
        runtime,
        uv_path=str(fake_uv(tmp_path, fail_install=True)),
        worker_script=fake_probe_worker(tmp_path),
        allow_development_python=False,
    )

    with pytest.raises(LocalRuntimeError, match="simulated network failure"):
        manager.install_all()

    assert marker.read_text(encoding="utf-8") == "healthy"
    assert not list(runtime.glob(".staging-*"))

    manager.uv_path = str(fake_uv(tmp_path))
    assert manager.install_all().healthy


def test_pre_canceled_install_leaves_runtime_untouched(tmp_path: Path) -> None:
    manager = LocalRuntimeManager(
        tmp_path / "runtime",
        uv_path=str(fake_uv(tmp_path)),
        worker_script=fake_probe_worker(tmp_path),
        allow_development_python=False,
    )
    token = CancellationToken()
    token.cancel()

    with pytest.raises(TaskCancelledError):
        manager.install_whisper(cancellation_token=token)

    assert not manager.active_dir.exists()


def test_remove_runtime_updates_status(tmp_path: Path) -> None:
    manager = LocalRuntimeManager(
        tmp_path / "runtime",
        uv_path=str(fake_uv(tmp_path)),
        worker_script=fake_probe_worker(tmp_path),
        allow_development_python=False,
    )
    manager.install_all()

    manager.remove()

    assert manager.probe().healthy is False
    assert not manager.active_dir.exists()


def test_external_python_selection_is_persisted(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    worker = fake_probe_worker(tmp_path)
    manager = LocalRuntimeManager(runtime, worker_script=worker, allow_development_python=False)

    status = manager.set_external_python(sys.executable)
    reloaded = LocalRuntimeManager(runtime, worker_script=worker, allow_development_python=False)

    assert status.source == "external"
    assert reloaded.external_python
    assert reloaded.probe().healthy
