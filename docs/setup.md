# Setup

[Korean documentation](setup.ko.md)

Installation and provider setup for Lecture Auto.

## Requirements

- Python 3.11+
- FFmpeg
- A supported capture backend: macOS AVFoundation, Windows DirectShow, or Linux PulseAudio/ALSA
- A loopback or monitor device for system-audio recording, such as:
  - BlackHole
  - Loopback
  - Soundflower
- An STT API key when using cloud STT
- A Google API key from AI Studio when using hosted Gemini or Gemma 4 models
- An Ollama server and model when using Ollama

## Install

```bash
git clone https://github.com/fullsack73/lecture-auto.git
cd lecture-auto
pip install -e .
```

Check the installed commands:

```bash
lecture-auto --help
lecture_auto --help
```

Run directly from a source checkout:

```bash
PYTHONPATH=src python -m lecture_auto.cli --help
```

## Install the Windows or Linux Desktop App

Download the matching 64-bit installer from the [latest GitHub Release](https://github.com/fullsack73/lecture-auto/releases/latest). FFmpeg and FFprobe are bundled.

- Windows: run `LectureAuto-Setup.exe`. The installer is not code-signed, so SmartScreen may ask for confirmation.
- Linux AppImage: run `chmod +x LectureAuto-linux-x86_64.AppImage`, then launch the file.
- Linux portable archive: extract `LectureAuto-linux-x86_64.tar.gz`, then run `LectureAuto.dist/LectureAuto`.

API keys and the workspace are configured inside the app after installation. Windows/Linux packages are built automatically from version tags; SHA-256 values are published as `SHA256SUMS.txt` in the same Release.

## Build the macOS Desktop App Locally

GitHub Releases currently provide Windows and Linux installers. macOS users build the app on a Mac that meets these requirements:

- Apple silicon (`uname -m` prints `arm64`)
- An ARM64 Python 3.11 or newer
- Xcode Command Line Tools
- The Rust toolchain
- Enough free disk space for build files and network access to download FFmpeg sources

Clone the repository once:

```bash
git clone https://github.com/fullsack73/lecture-auto.git
cd lecture-auto
```

Install Command Line Tools and Rust if they are missing:

```bash
xcode-select --install
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Open a new terminal, then build from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[build]'
scripts/build_macos_app.sh --install
```

The installed app is available at `/Applications/Lecture Auto.app`:

```bash
open "/Applications/Lecture Auto.app"
```

To build without installing into Applications, omit `--install`:

```bash
scripts/build_macos_app.sh
open build/macos/LectureAuto.app
```

The first FFmpeg/Nuitka build can take some time. The script prepares ARM64 FFmpeg/FFprobe from source, bundles them with the app, and applies an ad-hoc signature for local execution. The result is not a Developer ID-signed or Apple-notarized public release and is intended for use on the Mac where it was built.

If the build reports `This build script requires a native arm64 shell`, verify that neither the shell nor Python is running through Rosetta:

```bash
uname -m
python -c 'import platform; print(platform.machine())'
```

## Build the Windows Desktop App Locally

The native Windows build supports x86_64 Windows with Python 3.11 or newer. Install the C/C++ build tools requested by Nuitka and optionally Inno Setup 6 for an installer. From PowerShell in the repository root:

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
./scripts/build_windows_app.ps1
./build/windows/LectureAuto.dist/LectureAuto.exe
```

To build the installer:

```powershell
./scripts/build_windows_app.ps1 -Installer
./dist-installer/LectureAuto-Setup.exe
```

The script downloads a pinned x86_64 LGPL FFmpeg build, validates its SHA-256, DirectShow and MP3 support, and bundles FFmpeg license/source notices. The packaged GUI is smoke-launched before the build succeeds.

## Build the Linux Desktop App Locally

Linux builds support x86_64 and ARM64 with Python 3.11 or newer. Install a compiler, `patchelf`, and common archive tools. For Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y build-essential python3-dev patchelf curl \
  libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 \
  libxcb-xkb1 libxkbcommon-x11-0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[build]'
bash scripts/build_linux_app.sh
build/linux/LectureAuto.dist/LectureAuto
```

The normal build also creates `dist-release/LectureAuto-linux-<arch>.tar.gz`. To create an AppImage:

```bash
bash scripts/build_linux_app.sh --appimage
```

The Linux build bundles a pinned LGPL FFmpeg/FFprobe pair and checks for PulseAudio or ALSA capture, MP3 support, license notices, and a headless GUI smoke launch. AppImage packaging uses a checksum-pinned `linuxdeploy` asset.

## Workspace

The default workspace is `~/.lecture_auto`.

Set a default workspace:

```bash
lecture-auto config set --workspace ./lecture_data
```

Override it for one command:

```bash
lecture-auto --workspace ./lecture_data session history
```

Use an environment variable:

```bash
export LECTURE_AUTO_WORKSPACE="$PWD/lecture_data"
```

## STT Setup

### Deepgram

```bash
lecture-auto config set \
  --stt-mode api \
  --stt-api-provider deepgram \
  --stt-api-key "your-deepgram-key" \
  --stt-language korean
```

### OpenAI-Compatible STT

```bash
lecture-auto config set \
  --stt-mode api \
  --stt-api-provider openai-compatible \
  --stt-api-key "your-stt-key" \
  --stt-language korean
```

### Local Whisper

```bash
lecture-auto config set \
  --stt-mode local \
  --stt-local-model large-v3 \
  --stt-language korean
```

## LLM Setup

### Google API

Google API is the default LLM provider. It uses the `gemini` provider value for compatibility and supports hosted Gemini and Gemma 4 model IDs.

```bash
lecture-auto config set \
  --gemini-api-key "your-google-api-key" \
  --llm-model gemma-4-26b-a4b-it \
  --llm-thinking-level medium \
  --llm-language korean
```

Supported model presets:

```text
gemini-3.1-flash-lite
gemini-3-flash-preview
gemini-3.1-pro-preview
gemma-4-26b-a4b-it
gemma-4-31b-it
```

### Ollama

Ollama does not require an API key. The Ollama server must be running and the target model must be available.

```bash
LLM_PROVIDER=ollama LLM_MODEL=gemma4:31b-cloud lecture-auto summarize --id week-01
```

You can also set the LLM provider to `local`/`ollama` from the TUI Config menu.

Ollama note generation does not ask the model to write Markdown directly.

```text
transcript
-> section JSON generation
-> validation
-> optional repair
-> structured Markdown render
```

This reduces template drift when smaller models ignore Markdown instructions.

## Capture Setup

Microphone recording:

```bash
lecture-auto config set --capture-source microphone
```

System audio recording:

```bash
lecture-auto config set --capture-source system_audio
```

System audio on macOS may require a loopback device.

## Audio Refinement

Dynamic normalization during STT preprocessing:

```bash
lecture-auto config set --use-dynaudnorm
```

Normalize a session recording:

```bash
lecture-auto session refine-audio week-01
```

Run DeepFilterNet noise reduction:

```bash
lecture-auto session refine-noise week-01
```

## Common Environment Variables

```text
LECTURE_AUTO_WORKSPACE
LECTURE_AUTO_CAPTURE_SOURCE
LECTURE_AUTO_AUDIO_FORMAT
STT_MODE
STT_API_PROVIDER
STT_API_KEY
STT_LOCAL_MODEL
USE_DYNAUDNORM
LLM_PROVIDER
LLM_MODEL
LLM_THINKING_LEVEL
GEMINI_API_KEY
```

## Troubleshooting

### `No LLM adapter configured`

Google API key is missing, or Ollama provider/model config is wrong.

Google API:

```bash
lecture-auto config set --gemini-api-key "your-google-api-key"
```

Ollama:

```bash
LLM_PROVIDER=ollama LLM_MODEL=<model> lecture-auto summarize --id <session_id>
```

### `Transcription config error`

Check STT mode, provider, and API key.

```bash
lecture-auto config show
```

### Recording Fails

Check FFmpeg and macOS audio permissions.

```bash
ffmpeg -version
```

For system audio recording, also check your loopback device setup.

### PPT/PPTX Material Import Fails

PPT/PPTX conversion may require LibreOffice. For the simplest path, convert slides to PDF first and import the PDF.
