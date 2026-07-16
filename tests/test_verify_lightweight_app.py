import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_lightweight_app.py"
SPEC = importlib.util.spec_from_file_location("verify_lightweight_app", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
verify = MODULE.verify


def test_verify_rejects_note_template_outside_runtime_package_path(tmp_path: Path) -> None:
    app = tmp_path / "LectureAuto.app"
    executable = app / "Contents" / "MacOS" / "LectureAuto"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"placeholder")
    misplaced_template = executable.parent / "templates" / "structured-notes.md"
    misplaced_template.parent.mkdir(parents=True)
    misplaced_template.write_text("## Topic Overview", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Bundled note template not found"):
        verify(app, tmp_path / "nuitka-report.xml")
