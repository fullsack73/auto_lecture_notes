from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as host_platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import NamedTuple


RELEASE_TAG = "autobuild-2026-06-30-13-34"
FFMPEG_REVISION = "9a01c1cb6a"


class ArchiveSpec(NamedTuple):
    asset: str
    sha256: str
    archive_type: str

    @property
    def url(self) -> str:
        return (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
            f"{RELEASE_TAG}/{self.asset}"
        )


ARCHIVES = {
    ("windows", "x86_64"): ArchiveSpec(
        "ffmpeg-N-125365-g9a01c1cb6a-win64-lgpl.zip",
        "75cb786fa14299eb1c1cacc2542a15c8da690e551ab41858383dc425c605b8ab",
        "zip",
    ),
    ("linux", "x86_64"): ArchiveSpec(
        "ffmpeg-N-125365-g9a01c1cb6a-linux64-lgpl.tar.xz",
        "5a52f6d396da47ba48164c85591e11078dcb3cd8fadde7d79956dcccb3d3868a",
        "tar.xz",
    ),
    ("linux", "arm64"): ArchiveSpec(
        "ffmpeg-N-125365-g9a01c1cb6a-linuxarm64-lgpl.tar.xz",
        "9effc847f9deac1163e72c7ed2385c562051229f072183959ed53a2747c2fe0e",
        "tar.xz",
    ),
}

LICENSE_FILES = {
    "COPYING.LGPLv2.1": (
        f"https://raw.githubusercontent.com/FFmpeg/FFmpeg/{FFMPEG_REVISION}/COPYING.LGPLv2.1",
        "246041b6ecf9bc32d718a62c57877c78b5eb397b6467e74ed7ae2626ab189c30",
    ),
    "LICENSE.md": (
        f"https://raw.githubusercontent.com/FFmpeg/FFmpeg/{FFMPEG_REVISION}/LICENSE.md",
        "2e1d16c72fd74e12063776371da757322f8b77589386532f4fd8634bde7de1af",
    ),
}


def normalized_architecture(value: str) -> str:
    return {
        "amd64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
    }.get(value.lower(), value.lower())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_sha256: str) -> None:
    if destination.is_file() and sha256(destination) == expected_sha256:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    partial.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Lecture-Auto-build"})
    with urllib.request.urlopen(request) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    actual = sha256(partial)
    if actual != expected_sha256:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"Checksum mismatch for {url}: expected {expected_sha256}, got {actual}"
        )
    partial.replace(destination)


def _wanted_archive_name(name: str, executable_names: set[str]) -> str | None:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.name in executable_names and path.parent.name == "bin":
        return f"bin/{path.name}"
    lowered = path.name.lower()
    if (
        path.is_absolute()
        or ".." in path.parts
        or not lowered
        or path.name in executable_names
    ):
        return None
    if any(token in lowered for token in ("license", "copying", "notice")):
        return f"licenses/upstream-package/{path.name}"
    return None


def extract_selected(archive: Path, archive_type: str, destination: Path, platform: str) -> None:
    executable_names = (
        {"ffmpeg.exe", "ffprobe.exe"}
        if platform == "windows"
        else {"ffmpeg", "ffprobe"}
    )
    selected: dict[str, bytes] = {}
    if archive_type == "zip":
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                target = _wanted_archive_name(member.filename, executable_names)
                if target and not member.is_dir():
                    selected.setdefault(target, package.read(member))
    else:
        with tarfile.open(archive, mode="r:xz") as package:
            for member in package.getmembers():
                target = _wanted_archive_name(member.name, executable_names)
                if target and member.isfile():
                    extracted = package.extractfile(member)
                    if extracted is not None:
                        selected.setdefault(target, extracted.read())

    missing = executable_names.difference(PurePosixPath(name).name for name in selected)
    if missing:
        raise RuntimeError(f"FFmpeg archive is missing required tools: {sorted(missing)}")

    if destination.exists():
        shutil.rmtree(destination)
    for relative, content in selected.items():
        output = destination / Path(relative)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        if output.parent.name == "bin" and platform != "windows":
            output.chmod(output.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def validate_tools(destination: Path, platform: str) -> None:
    suffix = ".exe" if platform == "windows" else ""
    ffmpeg = destination / "bin" / f"ffmpeg{suffix}"
    ffprobe = destination / "bin" / f"ffprobe{suffix}"
    for tool in (ffmpeg, ffprobe):
        if not tool.is_file():
            raise RuntimeError(f"Prepared media tool not found: {tool}")
    version = subprocess.check_output([str(ffmpeg), "-version"], text=True, errors="replace")
    if "--enable-gpl" in version or "--enable-nonfree" in version:
        raise RuntimeError("Prepared FFmpeg enables GPL or nonfree components")
    if "--enable-libmp3lame" not in version:
        raise RuntimeError("Prepared FFmpeg does not support MP3 encoding")
    devices = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-devices"],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )
    expected = "dshow" if platform == "windows" else ("pulse", "alsa")
    combined = devices.stdout + devices.stderr
    if isinstance(expected, tuple):
        if not any(name in combined for name in expected):
            raise RuntimeError("Prepared FFmpeg has neither PulseAudio nor ALSA capture support")
    elif expected not in combined:
        raise RuntimeError(f"Prepared FFmpeg does not support the {expected} capture backend")


def prepare(
    root: Path,
    platform: str,
    architecture: str,
    destination: Path | None = None,
) -> Path:
    key = (platform, normalized_architecture(architecture))
    try:
        spec = ARCHIVES[key]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported FFmpeg desktop target: {key[0]} {key[1]}") from exc
    output = destination or root / "build" / "dependencies" / f"ffmpeg-lgpl-{platform}-{key[1]}"
    archive = root / "build" / "downloads" / spec.asset
    download(spec.url, archive, spec.sha256)
    extract_selected(archive, spec.archive_type, output, platform)

    license_dir = output / "licenses"
    license_dir.mkdir(parents=True, exist_ok=True)
    for name, (url, expected_sha256) in LICENSE_FILES.items():
        download(url, license_dir / name, expected_sha256)
    metadata = {
        "provider": "BtbN/FFmpeg-Builds",
        "release_tag": RELEASE_TAG,
        "ffmpeg_revision": FFMPEG_REVISION,
        "asset": spec.asset,
        "url": spec.url,
        "sha256": spec.sha256,
        "license": "LGPL-2.1-or-later",
        "target": {"platform": platform, "architecture": key[1]},
    }
    (license_dir / "SOURCE.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    validate_tools(output, platform)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("windows", "linux"), required=True)
    parser.add_argument("--architecture", default=normalized_architecture(host_platform.machine()))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = prepare(root, args.platform, args.architecture, args.output)
    print(json.dumps({"ffmpeg_root": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
