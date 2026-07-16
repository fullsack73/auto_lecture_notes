import importlib.util
import struct
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_lightweight_app.py"
SPEC = importlib.util.spec_from_file_location("verify_lightweight_app", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
verify = MODULE.verify
binary_architecture = MODULE.binary_architecture


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


def test_binary_architecture_reads_windows_pe_machine(tmp_path: Path) -> None:
    executable = tmp_path / "LectureAuto.exe"
    payload = bytearray(512)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    executable.write_bytes(payload)

    assert binary_architecture(executable, "windows") == "x86_64"


def test_binary_architecture_reads_linux_elf_machine(tmp_path: Path) -> None:
    executable = tmp_path / "LectureAuto"
    payload = bytearray(64)
    payload[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", payload, 18, 183)
    executable.write_bytes(payload)

    assert binary_architecture(executable, "linux") == "arm64"
