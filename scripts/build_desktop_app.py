from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from prepare_ffmpeg_desktop import normalized_architecture, prepare


APP_VERSION = "0.1.3"


def native_platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    raise RuntimeError("This builder only supports native Windows and Linux builds")


def required_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise RuntimeError(f"{label} not found: {path}")
    return path


def build(platform_name: str | None = None, *, smoke_test: bool = True) -> Path:
    selected_platform = platform_name or native_platform()
    if selected_platform != native_platform():
        raise RuntimeError("Desktop applications must be built natively; cross-compilation is not supported")
    architecture = normalized_architecture(platform.machine())
    if selected_platform == "windows" and architecture != "x86_64":
        raise RuntimeError("The Windows desktop build currently supports x86_64 only")
    if selected_platform == "linux" and architecture not in {"x86_64", "arm64"}:
        raise RuntimeError("The Linux desktop build supports x86_64 and arm64")

    root = Path(__file__).resolve().parents[1]
    build_dir = root / "build" / selected_platform
    source = required_file(root / "src" / "lecture_auto" / "gui" / "LectureAuto.py", "GUI entry point")
    icon = required_file(root / "src" / "lecture_auto" / "gui" / "assets" / "app-icon.png", "Application icon")
    uv_name = "uv.exe" if selected_platform == "windows" else "uv"
    uv = Path(shutil.which(uv_name) or (Path(sys.executable).parent / uv_name))
    required_file(uv, "uv build binary")
    ffmpeg_root = prepare(root, selected_platform, architecture)
    executable_suffix = ".exe" if selected_platform == "windows" else ""

    data_files = {
        root / "src" / "lecture_auto" / "local_ai_worker.py": "local_ai_worker.py",
        root / "src" / "lecture_auto" / "gemini_addon_worker.py": "gemini_addon_worker.py",
        root / "src" / "lecture_auto" / "__init__.py": "addon_source/lecture_auto/__init__.py",
        root / "src" / "lecture_auto" / "llm_adapter.py": "addon_source/lecture_auto/llm_adapter.py",
        root / "src" / "lecture_auto" / "llm_config.py": "addon_source/lecture_auto/llm_config.py",
        root / "src" / "lecture_auto" / "templates" / "structured-notes.md": "lecture_auto/templates/structured-notes.md",
        uv: f"bin/{uv_name}",
        ffmpeg_root / "bin" / f"ffmpeg{executable_suffix}": f"bin/ffmpeg{executable_suffix}",
        ffmpeg_root / "bin" / f"ffprobe{executable_suffix}": f"bin/ffprobe{executable_suffix}",
        icon: "assets/app-icon.png",
    }
    for path in data_files:
        required_file(path, "Bundled build input")

    build_dir.mkdir(parents=True, exist_ok=True)
    for name in ("LectureAuto.build", "LectureAuto.dist", "LectureAuto.onefile-build"):
        candidate = build_dir / name
        if candidate.exists():
            shutil.rmtree(candidate)
    report = build_dir / "nuitka-report.xml"
    report.unlink(missing_ok=True)

    command = [
        sys.executable,
        "-m",
        "nuitka",
        str(source),
        "--enable-plugin=pyside6",
        "--standalone",
        f"--output-dir={build_dir}",
        "--output-filename=LectureAuto",
        "--output-folder-name=LectureAuto",
        "--module-parameter=torch-disable-jit=yes",
        "--no-prefer-source-code",
        "--nofollow-import-to=torch",
        "--nofollow-import-to=torchaudio",
        "--nofollow-import-to=faster_whisper",
        "--nofollow-import-to=ctranslate2",
        "--nofollow-import-to=df",
        "--nofollow-import-to=onnxruntime",
        "--nofollow-import-to=google.genai",
        "--nofollow-import-to=google.api_core",
        f"--include-data-dir={ffmpeg_root / 'licenses'}=licenses/ffmpeg",
        f"--report={report}",
        "--assume-yes-for-downloads",
    ]
    if selected_platform == "windows":
        from PIL import Image

        windows_icon = build_dir / "app-icon.ico"
        with Image.open(icon) as source_icon:
            source_icon.save(
                windows_icon,
                format="ICO",
                sizes=((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)),
            )
        command.extend(
            (
                "--windows-console-mode=disable",
                f"--windows-icon-from-ico={windows_icon}",
                f"--file-version={APP_VERSION}",
                f"--product-version={APP_VERSION}",
                "--product-name=Lecture Auto",
                "--company-name=Lecture Auto",
                "--file-description=Lecture Auto desktop application",
            )
        )
    for source_path, target in data_files.items():
        command.append(f"--include-data-file={source_path}={target}")

    started_at = int(time.time())
    subprocess.run(command, cwd=root, check=True)
    app = build_dir / "LectureAuto.dist"
    executable = app / f"LectureAuto{executable_suffix}"
    required_file(executable, "Built application executable")
    verifier = root / "scripts" / "verify_lightweight_app.py"
    verify_command = [
        sys.executable,
        str(verifier),
        "--app",
        str(app),
        "--report",
        str(report),
        "--platform",
        selected_platform,
        "--architecture",
        architecture,
    ]
    if smoke_test:
        verify_command.append("--smoke-test")
    subprocess.run(verify_command, cwd=root, check=True)

    finished_at = int(time.time())
    size_bytes = sum(path.stat().st_size for path in app.rglob("*") if path.is_file())
    metadata = {
        "platform": selected_platform,
        "architecture": architecture,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": finished_at - started_at,
        "app_size_bytes": size_bytes,
        "app": str(app),
    }
    (build_dir / "build-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("windows", "linux"))
    parser.add_argument("--no-smoke-test", action="store_true")
    args = parser.parse_args()
    app = build(args.platform, smoke_test=not args.no_smoke_test)
    print(json.dumps({"app": str(app)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
