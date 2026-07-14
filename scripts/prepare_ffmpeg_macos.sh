#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPENDENCY_ROOT="${DEPENDENCY_ROOT:-$ROOT/build/dependencies}"
DOWNLOAD_DIR="$DEPENDENCY_ROOT/downloads"
SOURCE_DIR="$DEPENDENCY_ROOT/sources"
PREFIX="$DEPENDENCY_ROOT/ffmpeg-lgpl"
FFMPEG_VERSION="7.1.5"
LAME_VERSION="3.100"
FFMPEG_ARCHIVE="ffmpeg-$FFMPEG_VERSION.tar.xz"
LAME_ARCHIVE="lame-$LAME_VERSION.tar.gz"
FFMPEG_SHA256="de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f"
LAME_SHA256="ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e"
FFMPEG_URL="https://ffmpeg.org/releases/$FFMPEG_ARCHIVE"
LAME_URL="https://download.videolan.org/pub/contrib/lame/$LAME_ARCHIVE"
JOBS="${JOBS:-$(sysctl -n hw.logicalcpu)}"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  print -u2 "This dependency build requires macOS arm64."
  exit 2
fi

verify_binary() {
  [[ -x "$PREFIX/bin/ffmpeg" && -x "$PREFIX/bin/ffprobe" ]] || return 1
  file "$PREFIX/bin/ffmpeg" | grep -q "arm64" || return 1
  "$PREFIX/bin/ffmpeg" -version 2>&1 | grep -q -- "--disable-gpl" || return 1
  "$PREFIX/bin/ffmpeg" -version 2>&1 | grep -q -- "--disable-nonfree" || return 1
  "$PREFIX/bin/ffmpeg" -version 2>&1 | grep -q -- "--enable-libmp3lame" || return 1
  "$PREFIX/bin/ffmpeg" -hide_banner -devices 2>&1 | grep -q "avfoundation" || return 1
  ! otool -L "$PREFIX/bin/ffmpeg" | grep -Eq '/opt/homebrew|/usr/local' || return 1
}

if verify_binary; then
  print "Prepared FFmpeg: $PREFIX/bin/ffmpeg"
  exit 0
fi

mkdir -p "$DOWNLOAD_DIR" "$SOURCE_DIR"

download_and_verify() {
  local url="$1"
  local target="$2"
  local expected="$3"
  if [[ ! -f "$target" ]]; then
    curl --fail --location --retry 3 "$url" --output "$target"
  fi
  local actual
  actual="$(shasum -a 256 "$target" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    print -u2 "Checksum mismatch: $target"
    print -u2 "Expected: $expected"
    print -u2 "Actual:   $actual"
    exit 3
  fi
}

download_and_verify "$FFMPEG_URL" "$DOWNLOAD_DIR/$FFMPEG_ARCHIVE" "$FFMPEG_SHA256"
download_and_verify "$LAME_URL" "$DOWNLOAD_DIR/$LAME_ARCHIVE" "$LAME_SHA256"

rm -rf "$SOURCE_DIR/ffmpeg-$FFMPEG_VERSION" "$SOURCE_DIR/lame-$LAME_VERSION" "$PREFIX"
tar -xf "$DOWNLOAD_DIR/$FFMPEG_ARCHIVE" -C "$SOURCE_DIR"
tar -xf "$DOWNLOAD_DIR/$LAME_ARCHIVE" -C "$SOURCE_DIR"
mkdir -p "$PREFIX"

pushd "$SOURCE_DIR/lame-$LAME_VERSION" >/dev/null
./configure \
  --prefix="$PREFIX" \
  --disable-shared \
  --enable-static \
  --disable-frontend
make -j"$JOBS"
make install
popd >/dev/null

pushd "$SOURCE_DIR/ffmpeg-$FFMPEG_VERSION" >/dev/null
PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" ./configure \
  --prefix="$PREFIX" \
  --arch=arm64 \
  --target-os=darwin \
  --cc=clang \
  --disable-debug \
  --disable-doc \
  --disable-ffplay \
  --disable-network \
  --disable-autodetect \
  --disable-gpl \
  --disable-nonfree \
  --enable-avfoundation \
  --enable-indev=avfoundation \
  --enable-audiotoolbox \
  --enable-libmp3lame \
  --enable-static \
  --disable-shared \
  --pkg-config-flags=--static \
  --extra-cflags="-I$PREFIX/include" \
  --extra-ldflags="-L$PREFIX/lib"
make -j"$JOBS"
make install
popd >/dev/null

mkdir -p "$PREFIX/licenses/ffmpeg" "$PREFIX/licenses/lame"
cp "$SOURCE_DIR/ffmpeg-$FFMPEG_VERSION/COPYING.LGPLv2.1" "$PREFIX/licenses/ffmpeg/"
cp "$SOURCE_DIR/ffmpeg-$FFMPEG_VERSION/LICENSE.md" "$PREFIX/licenses/ffmpeg/"
cp "$SOURCE_DIR/lame-$LAME_VERSION/COPYING" "$PREFIX/licenses/lame/"
cp "$SOURCE_DIR/lame-$LAME_VERSION/LICENSE" "$PREFIX/licenses/lame/"
printf '%s\n' \
  "FFmpeg $FFMPEG_VERSION source: $FFMPEG_URL" \
  "SHA-256: $FFMPEG_SHA256" \
  "LAME $LAME_VERSION source: $LAME_URL" \
  "SHA-256: $LAME_SHA256" \
  > "$PREFIX/licenses/SOURCES.txt"

if ! verify_binary; then
  print -u2 "Prepared FFmpeg failed architecture, license, device, or linkage verification."
  exit 4
fi

print "Prepared FFmpeg: $PREFIX/bin/ffmpeg"
