from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install_macos_app.py"
SPEC = importlib.util.spec_from_file_location("install_macos_app", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_app(path: Path, marker: str) -> Path:
    executable = path / "Contents" / "MacOS" / "LectureAuto"
    executable.parent.mkdir(parents=True)
    executable.write_text(marker, encoding="utf-8")
    return path


def test_matching_pids_only_returns_installed_app_processes() -> None:
    executable = Path("/Applications/Lecture Auto.app/Contents/MacOS/LectureAuto")
    process_table = """\
  100 /Applications/Lecture Auto.app/Contents/MacOS/LectureAuto
  101 /Applications/Lecture Auto.app/Contents/MacOS/LectureAuto --help
  102 /Applications/lecture_auto/build/macos/LectureAuto.app/Contents/MacOS/LectureAuto
"""

    assert MODULE._matching_pids(executable, process_table) == [100, 101]


def test_install_refuses_to_replace_running_app(tmp_path: Path, monkeypatch) -> None:
    source = make_app(tmp_path / "build.app", "new")
    target = make_app(tmp_path / "installed.app", "old")
    monkeypatch.setattr(MODULE, "running_pids", lambda _target: [123])

    with pytest.raises(RuntimeError, match="Quit the app before reinstalling"):
        MODULE.install(source, target)

    assert (target / "Contents" / "MacOS" / "LectureAuto").read_text() == "old"


def test_install_replaces_closed_app_after_staging(tmp_path: Path, monkeypatch) -> None:
    source = make_app(tmp_path / "build.app", "new")
    target = make_app(tmp_path / "installed.app", "old")
    monkeypatch.setattr(MODULE, "running_pids", lambda _target: [])
    monkeypatch.setattr(
        MODULE,
        "_copy_and_verify",
        lambda source_app, candidate: shutil.copytree(source_app, candidate),
    )

    MODULE.install(source, target)

    assert (target / "Contents" / "MacOS" / "LectureAuto").read_text() == "new"
    assert not list(tmp_path.glob(".installed-install-*"))


def test_install_keeps_closed_app_when_staging_fails(tmp_path: Path, monkeypatch) -> None:
    source = make_app(tmp_path / "build.app", "new")
    target = make_app(tmp_path / "installed.app", "old")
    monkeypatch.setattr(MODULE, "running_pids", lambda _target: [])

    def fail_copy(_source: Path, _candidate: Path) -> None:
        raise RuntimeError("copy failed")

    monkeypatch.setattr(MODULE, "_copy_and_verify", fail_copy)

    with pytest.raises(RuntimeError, match="copy failed"):
        MODULE.install(source, target)

    assert (target / "Contents" / "MacOS" / "LectureAuto").read_text() == "old"
    assert not list(tmp_path.glob(".installed-install-*"))


def test_candidate_smoke_test_forces_ollama_import(tmp_path: Path, monkeypatch) -> None:
    app = make_app(tmp_path / "candidate.app", "new")
    observed = {}

    def run(command, **kwargs):
        observed["command"] = command
        observed["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", run)

    MODULE._smoke_test(app)

    assert observed["command"] == [
        str(app / "Contents" / "MacOS" / "LectureAuto")
    ]
    assert observed["env"]["LLM_PROVIDER"] == "ollama"
    assert observed["env"]["LECTURE_AUTO_SMOKE_TEST"] == "1"


def test_install_restores_previous_app_when_swap_fails(tmp_path: Path, monkeypatch) -> None:
    source = make_app(tmp_path / "build.app", "new")
    target = make_app(tmp_path / "installed.app", "old")
    monkeypatch.setattr(MODULE, "running_pids", lambda _target: [])
    monkeypatch.setattr(
        MODULE,
        "_copy_and_verify",
        lambda source_app, candidate: shutil.copytree(source_app, candidate),
    )
    original_rename = Path.rename

    def fail_candidate_swap(path: Path, destination: Path) -> Path:
        if path.name == target.name and path.parent.name.startswith(".installed-install-"):
            raise OSError("swap failed")
        return original_rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail_candidate_swap)

    with pytest.raises(OSError, match="swap failed"):
        MODULE.install(source, target)

    assert (target / "Contents" / "MacOS" / "LectureAuto").read_text() == "old"
    assert not list(tmp_path.glob(".installed-install-*"))
