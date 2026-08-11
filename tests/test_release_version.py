from pathlib import Path

from scripts.project_version import read_project_version


def test_release_builders_use_pyproject_version() -> None:
    root = Path(__file__).resolve().parents[1]

    assert read_project_version(root) == "0.1.5"
    assert '--macos-app-version="$APP_VERSION"' in (
        root / "scripts" / "build_macos_app.sh"
    ).read_text()
    assert '"/DAppVersion=$AppVersion"' in (
        root / "scripts" / "build_windows_app.ps1"
    ).read_text()
    assert "AppVersion={#AppVersion}" in (
        root / "deployment" / "windows.iss"
    ).read_text()
