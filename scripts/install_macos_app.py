from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _matching_pids(executable: Path, process_table: str) -> list[int]:
    prefix = f"{executable} "
    matches = []
    for line in process_table.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2:
            continue
        pid, command = fields
        if command == str(executable) or command.startswith(prefix):
            matches.append(int(pid))
    return matches


def running_pids(target: Path) -> list[int]:
    executable = target / "Contents" / "MacOS" / "LectureAuto"
    process_table = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return _matching_pids(executable, process_table)


def ensure_not_running(target: Path) -> None:
    pids = running_pids(target)
    if pids:
        raise RuntimeError(
            f"Lecture Auto is running (PID {', '.join(map(str, pids))}). "
            "Quit the app before reinstalling so recordings and background jobs are not interrupted."
        )


def _copy_and_verify(source: Path, candidate: Path) -> None:
    subprocess.run(["ditto", str(source), str(candidate)], check=True)
    subprocess.run(
        ["xattr", "-dr", "com.apple.quarantine", str(candidate)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(candidate)],
        check=True,
    )


def install(source: Path, target: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    executable = source / "Contents" / "MacOS" / "LectureAuto"
    if source.suffix != ".app" or not executable.is_file():
        raise RuntimeError(f"Invalid Lecture Auto app bundle: {source}")
    if target.suffix != ".app" or not target.parent.is_dir():
        raise RuntimeError(f"Invalid application install target: {target}")
    if source == target:
        raise RuntimeError("Build and install app paths must be different")

    ensure_not_running(target)
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{target.stem}-install-", dir=target.parent)
    )
    candidate = staging_root / target.name
    previous = staging_root / "previous.app"
    preserve_staging = False
    try:
        _copy_and_verify(source, candidate)
        had_previous = os.path.lexists(target)
        if had_previous:
            target.rename(previous)
        try:
            candidate.rename(target)
        except BaseException:
            if had_previous and not os.path.lexists(target):
                try:
                    previous.rename(target)
                except BaseException as restore_error:
                    preserve_staging = True
                    raise RuntimeError(
                        f"Installation failed and the previous app is preserved at {previous}"
                    ) from restore_error
            raise
    finally:
        if not preserve_staging:
            shutil.rmtree(staging_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("target", type=Path)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("source", type=Path)
    install_parser.add_argument("target", type=Path)
    args = parser.parse_args()

    try:
        if args.command == "check":
            ensure_not_running(args.target.resolve())
        else:
            install(args.source, args.target)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(4, f"macOS app install failed: {exc}\n")


if __name__ == "__main__":
    main()
