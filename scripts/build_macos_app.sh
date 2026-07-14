#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
BUILD_DIR="${BUILD_DIR:-$ROOT/build/macos}"
SOURCE="$ROOT/src/lecture_auto/gui/LectureAuto.py"
WORKER="$ROOT/src/lecture_auto/local_ai_worker.py"
GEMINI_WORKER="$ROOT/src/lecture_auto/gemini_addon_worker.py"
PACKAGE_INIT="$ROOT/src/lecture_auto/__init__.py"
LLM_ADAPTER="$ROOT/src/lecture_auto/llm_adapter.py"
LLM_CONFIG="$ROOT/src/lecture_auto/llm_config.py"
UV="$ROOT/.venv/bin/uv"
FFMPEG_ROOT="$ROOT/build/dependencies/ffmpeg-lgpl"
FFMPEG="$FFMPEG_ROOT/bin/ffmpeg"
FFPROBE="$FFMPEG_ROOT/bin/ffprobe"
ICON_PNG="$ROOT/src/lecture_auto/gui/assets/app-icon.png"
ICON_ICNS="$ROOT/src/lecture_auto/gui/assets/LectureAuto.icns"
APP="$BUILD_DIR/LectureAuto.app"
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

"$ROOT/scripts/prepare_ffmpeg_macos.sh"

if [[ ! -x "$FFMPEG" || ! -x "$FFPROBE" ]]; then
  print -u2 "Prepared FFmpeg tools not found under: $FFMPEG_ROOT/bin"
  exit 2
fi

mkdir -p "$BUILD_DIR"
STARTED_AT="$(date +%s)"
PREVIOUS_KB="$(du -sk "$BUILD_DIR" 2>/dev/null | awk '{print $1}' || print 0)"
rm -rf "$BUILD_DIR/app.build" "$BUILD_DIR/app.dist" "$BUILD_DIR/app.app" \
  "$BUILD_DIR/LectureAuto.build" "$BUILD_DIR/LectureAuto.dist" "$BUILD_DIR/LectureAuto.app"

# Nuitka's bundled ccache 4.2.1 is x86_64-only on this machine and causes
# xcrun to launch under Rosetta against arm64 Command Line Tools.
"$PYTHON" -m nuitka "$SOURCE" \
  --enable-plugin=pyside6 \
  --standalone \
  --macos-create-app-bundle \
  --macos-target-arch=arm64 \
  --macos-app-name="Lecture Auto" \
  --macos-signed-app-name="com.anarchytoast.lectureauto" \
  --macos-app-version=0.1.0 \
  --macos-app-icon="$ICON_ICNS" \
  --macos-app-protected-resource="NSMicrophoneUsageDescription:Lecture Auto records lecture audio selected by the user." \
  --output-dir="$BUILD_DIR" \
  --output-filename=LectureAuto \
  --output-folder-name=LectureAuto \
  --disable-cache=ccache \
  --module-parameter=torch-disable-jit=yes \
  --no-prefer-source-code \
  --nofollow-import-to=torch \
  --nofollow-import-to=torchaudio \
  --nofollow-import-to=faster_whisper \
  --nofollow-import-to=ctranslate2 \
  --nofollow-import-to=df \
  --nofollow-import-to=onnxruntime \
  --nofollow-import-to=google.genai \
  --nofollow-import-to=google.api_core \
  --include-data-file="$WORKER=local_ai_worker.py" \
  --include-data-file="$GEMINI_WORKER=gemini_addon_worker.py" \
  --include-data-file="$PACKAGE_INIT=addon_source/lecture_auto/__init__.py" \
  --include-data-file="$LLM_ADAPTER=addon_source/lecture_auto/llm_adapter.py" \
  --include-data-file="$LLM_CONFIG=addon_source/lecture_auto/llm_config.py" \
  --include-data-file="$UV=bin/uv" \
  --include-data-file="$FFMPEG=bin/ffmpeg" \
  --include-data-file="$FFPROBE=bin/ffprobe" \
  --include-data-dir="$FFMPEG_ROOT/licenses=licenses/ffmpeg" \
  --include-data-file="$ICON_PNG=assets/app-icon.png" \
  --report="$BUILD_DIR/nuitka-report.xml" \
  --assume-yes-for-downloads

if [[ ! -x "$APP/Contents/MacOS/LectureAuto" ]]; then
  print -u2 "Build completed without expected app executable: $APP"
  exit 3
fi

chmod +x "$APP/Contents/MacOS/bin/ffmpeg" "$APP/Contents/MacOS/bin/ffprobe"

"$PYTHON" "$ROOT/scripts/verify_lightweight_app.py" \
  --app "$APP" \
  --report "$BUILD_DIR/nuitka-report.xml"

codesign --force --deep --sign - --identifier "com.anarchytoast.lectureauto" "$APP"

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
