#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${PYTHON:-}" ]]; then
  PYTHON="$PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="$(command -v python3 || true)"
fi
APPIMAGE=false
PACKAGE_ONLY=false

if [[ "${1:-}" == "--appimage" ]]; then
  APPIMAGE=true
elif [[ "${1:-}" == "--appimage-only" ]]; then
  APPIMAGE=true
  PACKAGE_ONLY=true
elif [[ -n "${1:-}" ]]; then
  printf 'Unknown option: %s\n' "$1" >&2
  exit 2
fi

if [[ ! -x "$PYTHON" ]]; then
  printf 'Python environment not found: %s\n' "$PYTHON" >&2
  exit 2
fi

DIST="$ROOT/build/linux/LectureAuto.dist"
EXECUTABLE="$DIST/LectureAuto"
RELEASE_DIR="$ROOT/dist-release"
ARCH="$(uname -m)"
if [[ "$PACKAGE_ONLY" != true ]]; then
  "$PYTHON" "$ROOT/scripts/build_desktop_app.py" --platform linux
fi
if [[ ! -x "$EXECUTABLE" ]]; then
  printf 'Built application not found: %s\n' "$EXECUTABLE" >&2
  exit 3
fi

mkdir -p "$RELEASE_DIR"
if [[ "$PACKAGE_ONLY" != true ]]; then
  tar -C "$ROOT/build/linux" -czf "$RELEASE_DIR/LectureAuto-linux-$ARCH.tar.gz" LectureAuto.dist
fi

if [[ "$APPIMAGE" != true ]]; then
  printf 'Built application: %s\n' "$DIST"
  printf 'Built archive: %s\n' "$RELEASE_DIR/LectureAuto-linux-$ARCH.tar.gz"
  exit 0
fi

case "$ARCH" in
  x86_64|amd64)
    TOOL_ASSET_ID=462806018
    TOOL_SHA256=e87ee0815d109282fdda73e34c2361d64d02b0ffaea3674b18f1fd1f6a687dcf
    APPIMAGE_ARCH=x86_64
    ;;
  aarch64|arm64)
    TOOL_ASSET_ID=462805854
    TOOL_SHA256=650ed1d045a09ab87855be1963f4f56ac7cf6defb6b2e2f4af0a3225f3d2d803
    APPIMAGE_ARCH=aarch64
    ;;
  *)
    printf 'AppImage packaging is unsupported on architecture: %s\n' "$ARCH" >&2
    exit 2
    ;;
esac

APPDIR="$ROOT/build/linux/LectureAuto.AppDir"
TOOL="$ROOT/build/downloads/linuxdeploy-$APPIMAGE_ARCH.AppImage"
OUTPUT="$RELEASE_DIR/LectureAuto-linux-$APPIMAGE_ARCH.AppImage"
ICON_512="$ROOT/build/linux/app-icon-512.png"
"$PYTHON" "$ROOT/scripts/prepare_desktop_icon.py" \
  "$ROOT/src/lecture_auto/gui/assets/app-icon.png" "$ICON_512" --size 512
rm -rf "$APPDIR"
mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a "$DIST/." "$APPDIR/usr/bin/"
install -m 755 "$ROOT/deployment/linux/AppRun" "$APPDIR/AppRun"
install -m 644 "$ROOT/deployment/linux/lecture-auto.desktop" "$APPDIR/lecture-auto.desktop"
install -m 644 "$ROOT/deployment/linux/lecture-auto.desktop" "$APPDIR/usr/share/applications/lecture-auto.desktop"
install -m 644 "$ICON_512" "$APPDIR/lecture-auto.png"
install -m 644 "$ICON_512" "$APPDIR/usr/share/icons/hicolor/512x512/apps/lecture-auto.png"

if [[ ! -f "$TOOL" ]] || [[ "$(sha256sum "$TOOL" | awk '{print $1}')" != "$TOOL_SHA256" ]]; then
  rm -f "$TOOL"
  curl --fail --location \
    --header 'Accept: application/octet-stream' \
    --header 'X-GitHub-Api-Version: 2022-11-28' \
    --output "$TOOL" \
    "https://api.github.com/repos/linuxdeploy/linuxdeploy/releases/assets/$TOOL_ASSET_ID"
fi
if [[ "$(sha256sum "$TOOL" | awk '{print $1}')" != "$TOOL_SHA256" ]]; then
  printf 'linuxdeploy checksum validation failed: %s\n' "$TOOL" >&2
  exit 4
fi
chmod +x "$TOOL"
rm -f "$OUTPUT"
ARCH="$APPIMAGE_ARCH" LDAI_OUTPUT="$OUTPUT" APPIMAGE_EXTRACT_AND_RUN=1 \
  "$TOOL" --appdir "$APPDIR" --desktop-file "$APPDIR/lecture-auto.desktop" --icon-file "$APPDIR/lecture-auto.png" --output appimage

if [[ ! -x "$OUTPUT" ]]; then
  printf 'AppImage was not created: %s\n' "$OUTPUT" >&2
  exit 4
fi
APPIMAGE_EXTRACT_AND_RUN=1 \
LECTURE_AUTO_SMOKE_TEST=1 \
LECTURE_AUTO_WORKSPACE="${TMPDIR:-/tmp}/lecture-auto-appimage-smoke" \
QT_QPA_PLATFORM=offscreen \
HOME="${TMPDIR:-/tmp}/lecture-auto-appimage-home" \
"$OUTPUT"
printf 'Built AppImage: %s\n' "$OUTPUT"
