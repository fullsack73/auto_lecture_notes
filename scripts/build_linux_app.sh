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

TOOL_RELEASE=1-alpha-20251107-1
case "$ARCH" in
  x86_64|amd64)
    TOOL_SHA256=c20cd71e3a4e3b80c3483cef793cda3f4e990aca14014d23c544ca3ce1270b4d
    APPIMAGE_ARCH=x86_64
    ;;
  aarch64|arm64)
    TOOL_SHA256=620095110d693282b8ebeb244a95b5e911cf8f65f76c88b4b47d16ae6346fcff
    APPIMAGE_ARCH=aarch64
    ;;
  *)
    printf 'AppImage packaging is unsupported on architecture: %s\n' "$ARCH" >&2
    exit 2
    ;;
esac
TOOL_URL="https://github.com/linuxdeploy/linuxdeploy/releases/download/$TOOL_RELEASE/linuxdeploy-$APPIMAGE_ARCH.AppImage"

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
    --output "$TOOL" \
    "$TOOL_URL"
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
