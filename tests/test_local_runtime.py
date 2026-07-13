from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from lecture_auto.local_runtime import (
    LocalRuntimeError,
    LocalRuntimeManager,
    RuntimeStatus,
)
from lecture_auto.tasking import CancellationToken, TaskCancelledError


def make_executable(path: Path, text: str) -> Path:
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
        tmp_path / "uv",
        "#!/usr/bin/env python3\n"
        "import os,pathlib,sys\n"
        "args=sys.argv[1:]\n"
        f"fail={fail_install!r}\n"
        "if args and args[0]=='venv':\n"
        " p=pathlib.Path(args[1]); b=p/('Scripts' if os.name=='nt' else 'bin'); b.mkdir(parents=True,exist_ok=True); target=b/('python.exe' if os.name=='nt' else 'python'); target.symlink_to(sys.executable)\n"
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
    assert status.whisper_version == "1.2.0"


def test_architecture_mismatch_is_rejected(tmp_path: Path) -> None:
    wrong = "x86_64" if __import__("platform").machine() != "x86_64" else "arm64"
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
    assert (manager.active_dir / "bin" / "python").exists()
    assert not list(manager.runtime_dir.glob(".staging-*"))


def test_failed_install_preserves_existing_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    active_python = runtime / "active" / "bin" / "python"
    active_python.parent.mkdir(parents=True)
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
