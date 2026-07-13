#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
BUILD_DIR="${BUILD_DIR:-$ROOT/build/macos}"
SOURCE="$ROOT/src/lecture_auto/gui/app.py"
WORKER="$ROOT/src/lecture_auto/local_ai_worker.py"
UV="$ROOT/.venv/bin/uv"
# Nuitka derives the bundle directory from app.py; the installed copy below
# still receives the user-facing Lecture Auto.app name.
APP="$BUILD_DIR/app.app"
INSTALL_APP="/Applications/Lecture Auto.app"

if [[ "$(uname -m)" != "arm64" ]]; then
  print -u2 "This build script requires a native arm64 shell."
  exit 2
fi

if [[ ! -x "$PYTHON" ]]; then
  print -u2 "Python environment not found: $PYTHON"
  exit 2
fi

if [[ ! -x "$UV" ]]; then
  print -u2 "uv build binary not found: $UV"
  print -u2 "Install build dependencies with: $PYTHON -m pip install -e '$ROOT[build]'"
  exit 2
fi

if [[ "$($PYTHON -c 'import platform; print(platform.machine())')" != "arm64" ]]; then
  print -u2 "Python is not arm64: $PYTHON"
  exit 2
fi

mkdir -p "$BUILD_DIR"
STARTED_AT="$(date +%s)"
PREVIOUS_KB="$(du -sk "$BUILD_DIR" 2>/dev/null | awk '{print $1}' || print 0)"
rm -rf "$BUILD_DIR/app.build" "$BUILD_DIR/app.dist" "$BUILD_DIR/app.app" \
  "$BUILD_DIR/LectureAuto.build" "$BUILD_DIR/LectureAuto.dist" "$BUILD_DIR/LectureAuto.app"

"$PYTHON" -m nuitka "$SOURCE" \
  --enable-plugin=pyside6 \
  --standalone \
  --macos-create-app-bundle \
  --macos-target-arch=arm64 \
  --macos-app-name="Lecture Auto" \
  --macos-app-version=0.1.0 \
  --macos-app-protected-resource="NSMicrophoneUsageDescription:Lecture Auto records lecture audio selected by the user." \
  --output-dir="$BUILD_DIR" \
  --output-filename=LectureAuto \
  --disable-cache=ccache \
  --module-parameter=torch-disable-jit=yes \
  --no-prefer-source-code \
  --nofollow-import-to=torch \
  --nofollow-import-to=torchaudio \
  --nofollow-import-to=faster_whisper \
  --nofollow-import-to=ctranslate2 \
  --nofollow-import-to=df \
  --nofollow-import-to=onnxruntime \
  --include-data-file="$WORKER=local_ai_worker.py" \
  --include-data-file="$UV=bin/uv" \
  --report="$BUILD_DIR/nuitka-report.xml" \
  --assume-yes-for-downloads

if [[ ! -x "$APP/Contents/MacOS/LectureAuto" ]]; then
  print -u2 "Build completed without expected app executable: $APP"
  exit 3
fi

"$PYTHON" "$ROOT/scripts/verify_lightweight_app.py" \
  --app "$APP" \
  --report "$BUILD_DIR/nuitka-report.xml"

codesign --force --deep --sign - "$APP"

FINISHED_AT="$(date +%s)"
APP_KB="$(du -sk "$APP" | awk '{print $1}')"
printf '{"started_at":%s,"finished_at":%s,"duration_seconds":%s,"app_size_kb":%s,"previous_partial_size_kb":%s}\n' \
  "$STARTED_AT" "$FINISHED_AT" "$((FINISHED_AT-STARTED_AT))" "$APP_KB" "$PREVIOUS_KB" \
  > "$BUILD_DIR/build-metadata.json"

if [[ "${1:-}" == "--install" ]]; then
  if [[ -e "$INSTALL_APP" ]]; then
    rm -rf "$INSTALL_APP"
  fi
  ditto "$APP" "$INSTALL_APP"
  xattr -dr com.apple.quarantine "$INSTALL_APP" 2>/dev/null || true
  print "Installed: $INSTALL_APP"
else
  print "Built: $APP"
fi
