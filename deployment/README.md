# Desktop builds

Desktop applications are built natively with Nuitka; cross-compilation is not supported. Each build includes the note template, add-on worker sources, `uv`, an LGPL-compatible FFmpeg/FFprobe pair, and its license/source notices. The build fails if heavyweight optional AI packages leak into the base app or the packaged GUI does not pass a smoke launch.

Version tags matching `v*` build all native targets and publish the Windows x86_64 installer, Linux x86_64 AppImage/portable archive, and `SHA256SUMS.txt` to GitHub Releases. `workflow_dispatch` validates build artifacts without publishing a Release.

## macOS (Apple silicon)

```bash
scripts/build_macos_app.sh --install
open "/Applications/Lecture Auto.app"
```

Without `--install`, the result remains at `build/macos/LectureAuto.app`. The script builds verified ARM64 FFmpeg/FFprobe binaries from pinned sources, applies an ad-hoc signature, and does not create a Developer ID-signed or notarized release.

## Windows (x86_64)

```powershell
./scripts/build_windows_app.ps1
./build/windows/LectureAuto.dist/LectureAuto.exe
```

Pass `-Installer` when Inno Setup 6 is installed to create `dist-installer/LectureAuto-Setup.exe`:

```powershell
./scripts/build_windows_app.ps1 -Installer
```

## Linux (x86_64 or ARM64)

```bash
bash scripts/build_linux_app.sh
build/linux/LectureAuto.dist/LectureAuto
```

The script always creates a portable archive under `dist-release/`. Pass `--appimage` to also create an AppImage:

```bash
bash scripts/build_linux_app.sh --appimage
```

Windows/Linux FFmpeg binaries come from a pinned monthly BtbN LGPL build and are SHA-256 verified. Linux AppImage tooling is also fetched by immutable GitHub asset ID and checksum.
