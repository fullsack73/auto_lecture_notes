import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare_ffmpeg_desktop.py"
SPEC = importlib.util.spec_from_file_location("prepare_ffmpeg_desktop", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_desktop_ffmpeg_archives_are_pinned_and_lgpl() -> None:
    assert {platform for platform, _ in MODULE.ARCHIVES} == {"windows", "linux"}
    for spec in MODULE.ARCHIVES.values():
        assert "lgpl" in spec.asset
        assert len(spec.sha256) == 64
        assert "latest" not in spec.url


def test_archive_selection_keeps_only_tools_and_license_notices() -> None:
    executables = {"ffmpeg.exe", "ffprobe.exe"}

    assert MODULE._wanted_archive_name("package/bin/ffmpeg.exe", executables) == "bin/ffmpeg.exe"
    assert MODULE._wanted_archive_name("package/LICENSE.txt", executables) == "licenses/upstream-package/LICENSE.txt"
    assert MODULE._wanted_archive_name("package/bin/avcodec.dll", executables) is None
