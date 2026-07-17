from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


BANNED = (
    "torch",
    "torchaudio",
    "faster_whisper",
    "ctranslate2",
    "deepfilternet",
    "onnxruntime",
    "df",
    "google.genai",
    "google.api_core",
)
FILE_TOKENS = (
    "torch",
    "torchaudio",
    "faster_whisper",
    "ctranslate2",
    "deepfilter",
    "onnxruntime",
    "google_genai",
)


def banned_name(name: str) -> bool:
    normalized = name.lower().replace("-", "_")
    return any(normalized == value or normalized.startswith(value + ".") for value in BANNED)


def normalized_architecture(value: str) -> str:
    return {
        "amd64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
    }.get(value.lower(), value.lower())


def detect_platform(app: Path, platform_name: str | None) -> str:
    if platform_name:
        return platform_name
    if app.suffix == ".app":
        return "macos"
    if (app / "LectureAuto.exe").is_file():
        return "windows"
    return "linux"


def runtime_layout(app: Path, platform_name: str) -> tuple[Path, Path]:
    if platform_name == "macos":
        runtime_root = app / "Contents" / "MacOS"
        return runtime_root, runtime_root / "LectureAuto"
    executable = "LectureAuto.exe" if platform_name == "windows" else "LectureAuto"
    return app, app / executable


def binary_architecture(executable: Path, platform_name: str) -> str:
    data = executable.read_bytes()[:4096]
    if platform_name == "windows":
        if len(data) < 64 or data[:2] != b"MZ":
            raise RuntimeError(f"App executable is not a PE binary: {executable}")
        header_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if header_offset + 6 > len(data) or data[header_offset : header_offset + 4] != b"PE\0\0":
            raise RuntimeError(f"App executable has an invalid PE header: {executable}")
        machine = struct.unpack_from("<H", data, header_offset + 4)[0]
        return {0x8664: "x86_64", 0xAA64: "arm64"}.get(machine, f"pe-{machine:#x}")
    if platform_name == "linux":
        if len(data) < 20 or data[:4] != b"\x7fELF":
            raise RuntimeError(f"App executable is not an ELF binary: {executable}")
        byte_order = "<" if data[5] == 1 else ">"
        machine = struct.unpack_from(f"{byte_order}H", data, 18)[0]
        return {62: "x86_64", 183: "arm64"}.get(machine, f"elf-{machine}")
    description = subprocess.check_output(["file", str(executable)], text=True).strip().lower()
    if "arm64" in description or "aarch64" in description:
        return "arm64"
    if "x86_64" in description:
        return "x86_64"
    return description


def verify_smoke_launch(executable: Path, platform_name: str) -> None:
    with tempfile.TemporaryDirectory(prefix="lecture-auto-smoke-") as temp:
        env = dict(os.environ)
        env.update(
            {
                "LECTURE_AUTO_SMOKE_TEST": "1",
                "LECTURE_AUTO_WORKSPACE": str(Path(temp) / "workspace"),
                "HOME": temp,
                "USERPROFILE": temp,
            }
        )
        if platform_name == "linux" and not env.get("DISPLAY"):
            env["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [str(executable)],
            check=False,
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
        if result.returncode:
            output = (result.stdout + "\n" + result.stderr).strip()
            raise RuntimeError(
                f"Packaged GUI smoke test failed with exit code {result.returncode}: {output[-4000:]}"
            )


def verify(
    app: Path,
    report: Path,
    *,
    platform_name: str | None = None,
    architecture: str | None = None,
    smoke_test: bool = False,
) -> dict[str, object]:
    if not app.is_dir():
        raise RuntimeError(f"App bundle not found: {app}")
    selected_platform = detect_platform(app, platform_name)
    runtime_root, executable = runtime_layout(app, selected_platform)
    if not executable.is_file():
        raise RuntimeError(f"App executable not found: {executable}")
    note_template = runtime_root / "lecture_auto" / "templates" / "structured-notes.md"
    if not note_template.is_file():
        raise RuntimeError(f"Bundled note template not found: {note_template}")
    note_template_text = note_template.read_text(encoding="utf-8")
    if "## Topic Overview" not in note_template_text:
        raise RuntimeError(f"Bundled note template is invalid: {note_template}")

    for worker in ("local_ai_worker.py", "gemini_addon_worker.py"):
        if not (runtime_root / worker).is_file():
            raise RuntimeError(f"Bundled add-on worker not found: {runtime_root / worker}")
    uv_name = "uv.exe" if selected_platform == "windows" else "uv"
    if not (runtime_root / "bin" / uv_name).is_file():
        raise RuntimeError(f"Bundled uv executable not found: {runtime_root / 'bin' / uv_name}")

    bad_files = []
    for path in app.rglob("*"):
        if path.is_file() and any(token in path.name.lower().replace("-", "_") for token in FILE_TOKENS):
            bad_files.append(str(path.relative_to(app)))

    included_modules = []
    if report.is_file():
        root = ET.parse(report).getroot()
        for element in root.iter("module"):
            name = element.attrib.get("name", "")
            if banned_name(name):
                included_modules.append(name)

    if bad_files or included_modules:
        raise RuntimeError(
            "Local AI dependencies leaked into base app: "
            + json.dumps({"files": bad_files, "modules": sorted(set(included_modules))}, ensure_ascii=False)
        )

    actual_architecture = binary_architecture(executable, selected_platform)
    if architecture and normalized_architecture(actual_architecture) != normalized_architecture(architecture):
        raise RuntimeError(
            f"App executable architecture mismatch: expected {architecture}, got {actual_architecture}"
        )

    suffix = ".exe" if selected_platform == "windows" else ""
    media_tools = {}
    for name in ("ffmpeg", "ffprobe"):
        tool = runtime_root / "bin" / f"{name}{suffix}"
        if not tool.is_file():
            raise RuntimeError(f"Bundled media tool not found: {tool}")
        tool_architecture = binary_architecture(tool, selected_platform)
        if architecture and normalized_architecture(tool_architecture) != normalized_architecture(architecture):
            raise RuntimeError(
                f"Bundled media tool architecture mismatch: expected {architecture}, got {tool_architecture}"
            )
        media_tools[name] = str(tool.relative_to(app))

    license_dir = runtime_root / "licenses" / "ffmpeg"
    license_requirements = (
        ("COPYING.LGPLv2.1",),
        ("LICENSE.md",),
        ("SOURCE.json", "SOURCES.txt"),
    )
    bundled_license_files = {
        path.name for path in license_dir.rglob("*") if path.is_file()
    } if license_dir.is_dir() else set()
    for alternatives in license_requirements:
        if not any(name in bundled_license_files for name in alternatives):
            raise RuntimeError(
                f"Bundled FFmpeg license notice not found under {license_dir}: "
                + " or ".join(alternatives)
            )

    ffmpeg = runtime_root / "bin" / f"ffmpeg{suffix}"
    ffmpeg_version = subprocess.check_output(
        [str(ffmpeg), "-version"], text=True, errors="replace"
    )
    if "--enable-gpl" in ffmpeg_version or "--enable-nonfree" in ffmpeg_version:
        raise RuntimeError("Bundled FFmpeg enables GPL or nonfree components")
    if "--enable-libmp3lame" not in ffmpeg_version:
        raise RuntimeError("Bundled FFmpeg does not support MP3 encoding")
    devices = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-devices"],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )
    combined_devices = devices.stdout + devices.stderr
    expected_devices = {
        "macos": ("avfoundation",),
        "windows": ("dshow",),
        "linux": ("pulse", "alsa"),
    }[selected_platform]
    if not any(name in combined_devices for name in expected_devices):
        raise RuntimeError(
            f"Bundled FFmpeg lacks the expected capture backend: {', '.join(expected_devices)}"
        )

    if smoke_test:
        verify_smoke_launch(executable, selected_platform)

    size_bytes = sum(path.stat().st_size for path in app.rglob("*") if path.is_file())
    return {
        "app": str(app),
        "platform": selected_platform,
        "size_bytes": size_bytes,
        "architecture": actual_architecture,
        "banned_files": bad_files,
        "banned_modules": included_modules,
        "bundled_media_tools": media_tools,
        "bundled_note_template": str(note_template.relative_to(app)),
        "smoke_test": smoke_test,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--platform", choices=("macos", "windows", "linux"))
    parser.add_argument("--architecture")
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                args.app,
                args.report,
                platform_name=args.platform,
                architecture=args.architecture,
                smoke_test=args.smoke_test,
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
