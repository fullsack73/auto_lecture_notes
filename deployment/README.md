# Desktop builds

Prebuilt desktop binaries are not published. The supported desktop path is a local native build on an Apple Silicon Mac; desktop bundles are not cross-compiled.

```bash
xcode-select --install  # Skip if already installed.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[build]'
scripts/build_macos_app.sh --install
open "/Applications/Lecture Auto.app"
```

Without `--install`, the result remains at `build/macos/LectureAuto.app`. The script applies an ad-hoc signature for local execution; it does not create a Developer ID-signed or notarized release.

The macOS build runs `scripts/prepare_ffmpeg_macos.sh` and bundles verified arm64 FFmpeg/FFprobe binaries plus their license notices. The prepared build disables GPL/nonfree features, retains AVFoundation and MP3 support, and must not link to Homebrew paths.

Windows and Linux packaging is not an end-user distribution path. Any future local packaging work must copy FFmpeg/FFprobe to `lecture_auto/bin` (`.exe` on Windows), use an LGPL-compatible build, and ship its license notices.

The macOS script invokes Nuitka directly, forces a native arm64 target, and disables Nuitka's downloaded ccache. This avoids an x86_64 ccache binary trying to invoke arm64-only Command Line Tools.
