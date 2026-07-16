from __future__ import annotations

import argparse
import json
import subprocess
import sys
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


def verify(app: Path, report: Path) -> dict[str, object]:
    if not app.is_dir():
        raise RuntimeError(f"App bundle not found: {app}")
    executable = app / "Contents" / "MacOS" / "LectureAuto"
    if not executable.is_file():
        raise RuntimeError(f"App executable not found: {executable}")
    note_template = (
        app
        / "Contents"
        / "MacOS"
        / "lecture_auto"
        / "templates"
        / "structured-notes.md"
    )
    if not note_template.is_file():
        raise RuntimeError(f"Bundled note template not found: {note_template}")
    note_template_text = note_template.read_text(encoding="utf-8")
    if "## Topic Overview" not in note_template_text:
        raise RuntimeError(f"Bundled note template is invalid: {note_template}")

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

    size_bytes = sum(path.stat().st_size for path in app.rglob("*") if path.is_file())
    architecture = subprocess.check_output(["file", str(executable)], text=True).strip()
    if "arm64" not in architecture:
        raise RuntimeError(f"App executable is not arm64: {architecture}")
    media_tools = {}
    for name in ("ffmpeg", "ffprobe"):
        tool = app / "Contents" / "MacOS" / "bin" / name
        if not tool.is_file():
            raise RuntimeError(f"Bundled media tool not found: {tool}")
        tool_architecture = subprocess.check_output(["file", str(tool)], text=True).strip()
        if "arm64" not in tool_architecture:
            raise RuntimeError(f"Bundled media tool is not arm64: {tool_architecture}")
        media_tools[name] = str(tool.relative_to(app))
    ffmpeg = app / "Contents" / "MacOS" / "bin" / "ffmpeg"
    ffmpeg_version = subprocess.check_output([str(ffmpeg), "-version"], text=True)
    if "--disable-gpl" not in ffmpeg_version or "--disable-nonfree" not in ffmpeg_version:
        raise RuntimeError("Bundled FFmpeg is not the expected LGPL-compatible build")
    if "--enable-libmp3lame" not in ffmpeg_version:
        raise RuntimeError("Bundled FFmpeg does not support MP3 encoding")
    devices = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-devices"],
        check=False,
        capture_output=True,
        text=True,
    )
    if "avfoundation" not in devices.stdout + devices.stderr:
        raise RuntimeError("Bundled FFmpeg does not support AVFoundation capture")
    return {
        "app": str(app),
        "size_bytes": size_bytes,
        "architecture": architecture,
        "banned_files": bad_files,
        "banned_modules": included_modules,
        "bundled_media_tools": media_tools,
        "bundled_note_template": str(note_template.relative_to(app)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.app, args.report), ensure_ascii=False))


if __name__ == "__main__":
    main()
