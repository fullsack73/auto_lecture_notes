from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


BANNED = ("torch", "torchaudio", "faster_whisper", "ctranslate2", "deepfilternet", "onnxruntime", "df")
FILE_TOKENS = ("torch", "torchaudio", "faster_whisper", "ctranslate2", "deepfilter", "onnxruntime")


def banned_name(name: str) -> bool:
    normalized = name.lower().replace("-", "_")
    return any(normalized == value or normalized.startswith(value + ".") for value in BANNED)


def verify(app: Path, report: Path) -> dict[str, object]:
    if not app.is_dir():
        raise RuntimeError(f"App bundle not found: {app}")
    executable = app / "Contents" / "MacOS" / "LectureAuto"
    if not executable.is_file():
        raise RuntimeError(f"App executable not found: {executable}")

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
    return {
        "app": str(app),
        "size_bytes": size_bytes,
        "architecture": architecture,
        "banned_files": bad_files,
        "banned_modules": included_modules,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.app, args.report), ensure_ascii=False))


if __name__ == "__main__":
    main()
