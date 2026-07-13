# Desktop builds

Build on each target operating system; desktop bundles are not cross-compiled.

```bash
python -m pip install -e '.[build]'
scripts/build_macos_app.sh --install
```

Release artifacts:

- macOS: sign and notarize generated `LectureAuto.app`, then wrap it in a DMG.
- Windows: sign generated executable and package it with `deployment/windows.iss`.
- Linux: package generated standalone directory as AppImage with `linuxdeploy`.

FFmpeg must be copied to `lecture_auto/bin/ffmpeg` (`ffmpeg.exe` on Windows) before deployment. Use an LGPL-compatible build and ship its license notices.

The macOS script invokes Nuitka directly, forces a native arm64 target, and disables Nuitka's downloaded ccache. This avoids an x86_64 ccache binary trying to invoke arm64-only Command Line Tools.
