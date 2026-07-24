# Lecture Auto

[Korean documentation](docs/README.ko.md)

A desktop GUI, CLI, and TUI application that lets your computer attend class for you.

Lecture Auto records lecture audio, transcribes it, refines the transcript, and generates structured study notes. Instead of taking notes manually in real time, you can hand off the `recording -> transcript -> structured notes` flow to the program.

## What It Does

- Create and manage lecture sessions
- Record microphone or system audio
- Generate transcripts with STT
- Refine transcripts with an LLM
- Generate structured lecture notes with an LLM
- Attach PDF/PPT/PPTX course materials to sessions
- Search and open generated notes, transcripts, and recordings
- Use the desktop GUI, CLI commands, or the interactive TUI

Notes always use the `structured-notes` format. With Ollama, the model does not write Markdown directly; it generates section JSON, and the app renders the final Markdown.

## How to Install

Detailed installation and provider setup live in [docs/setup.md](docs/setup.md). Korean setup docs are available at [docs/setup.ko.md](docs/setup.ko.md).

### Download the Windows or Linux app

Prebuilt 64-bit packages are available on the [latest GitHub Release](https://github.com/fullsack73/lecture-auto/releases/latest):

- Windows installer: `LectureAuto-Setup.exe`
- Linux AppImage: `LectureAuto-linux-x86_64.AppImage`
- Linux portable archive: `LectureAuto-linux-x86_64.tar.gz`

FFmpeg and FFprobe are included. These packages are not code-signed, so Windows may display a SmartScreen warning. SHA-256 hashes are provided in `SHA256SUMS.txt`.

macOS and local development builds use the source instructions below.

Clone the repository first:

```bash
git clone https://github.com/fullsack73/lecture-auto.git
cd lecture-auto
```

### 1. Build and run the desktop app locally

Install Python 3.11+ and the Rust toolchain before building. Desktop builds are native rather than cross-compiled, so use the commands for the operating system where the app will run.

#### macOS (Apple silicon)

Install Xcode Command Line Tools first. Then build and install the app:

```bash
xcode-select --install  # Skip if Command Line Tools are already installed.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[build]'
scripts/build_macos_app.sh --install
open "/Applications/Lecture Auto.app"
```

The build bundles ARM64 FFmpeg/FFprobe and applies an ad-hoc signature for local use. It is not a Developer ID-signed or notarized public release. See [the macOS build guide](docs/setup.md#build-the-macos-desktop-app-locally) for requirements and troubleshooting.

#### Windows (x86_64)

From PowerShell, create the build environment and run the native build:

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
./scripts/build_windows_app.ps1
./build/windows/LectureAuto.dist/LectureAuto.exe
```

If Inno Setup 6 is installed, add `-Installer` to create `dist-installer/LectureAuto-Setup.exe`. See [the Windows build guide](docs/setup.md#build-the-windows-desktop-app-locally) for native compiler requirements.

#### Linux (x86_64 or ARM64)

After installing the compiler, `patchelf`, and the distribution packages listed in [the Linux build guide](docs/setup.md#build-the-linux-desktop-app-locally), run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[build]'
bash scripts/build_linux_app.sh
build/linux/LectureAuto.dist/LectureAuto
```

Add `--appimage` to create an AppImage as well as the portable tar archive. Windows and Linux builds bundle checksum-verified LGPL FFmpeg/FFprobe binaries and license notices.

The PySide6 desktop app shares its workspace and sessions with the CLI/TUI. It supports session management, capture, imports, audio cleanup, transcription, refinement, notes, library search, secure API-key storage, and local model management.

### 2. Install and use the CLI/TUI

Install Python 3.11+, FFmpeg, and Rust before installing from the source checkout. Some Python dependencies build native extensions and require the Rust toolchain. Install Rust from [rustup.rs](https://rustup.rs/), then restart your terminal so `cargo` is available on `PATH`.

```bash
python -m pip install -e .
```

Set the workspace and providers:

```bash
lecture-auto config set \
  --workspace ./lecture_data \
  --stt-language korean \
  --llm-language korean \
  --stt-mode api \
  --stt-api-provider deepgram \
  --stt-api-key "your-stt-key" \
  --gemini-api-key "your-google-api-key"
```

Open the interactive TUI:

```bash
lecture-auto
```

Run a complete session from the CLI:

```bash
lecture-auto session create \
  --session-id week-01 \
  --date 2026-05-08 \
  --title "Intro Lecture" \
  --course CS101

lecture-auto capture start week-01
lecture-auto capture stop week-01
lecture-auto transcription run week-01
lecture-auto summarize --id week-01
```

Generated files are stored under the active workspace.

```text
metadata/sessions.json
recordings/[course/]session-id.wav
transcripts/[course/]session-id-raw.md
transcripts/[course/]session-id-edited.md
materials/[course/]session-id.pdf
notes/[course/]session-id.md
```

## Main Workflow

1. Create a session
2. Record the lecture
3. Run STT
4. Refine the transcript
5. Generate notes
6. Check the results in the library

Transcript refinement is currently available from the TUI's Transcription menu. Note generation uses the best available transcript. If an edited transcript exists, it is preferred over the raw transcript.

## Commands

### TUI

```bash
lecture-auto
```

The easiest entry point. Use it to manage sessions, record audio, transcribe, refine transcripts, generate notes, browse the library, and update config.

### Config

```bash
lecture-auto config set [OPTIONS]
lecture-auto config show
```

Common options:

```bash
lecture-auto config set --workspace ./lecture_data
lecture-auto config set --stt-language korean --llm-language korean
lecture-auto config set --stt-mode api --stt-api-provider deepgram --stt-api-key "..."
lecture-auto config set --gemini-api-key "..." --llm-model gemma-4-26b-a4b-it
```

### Session

```bash
lecture-auto session create --session-id <id> --date <YYYY-MM-DD> [--title <title>] [--course <course>]
lecture-auto session history
lecture-auto session detail <session_id>
lecture-auto session update <session_id> [OPTIONS]
lecture-auto session delete <session_id>
lecture-auto session import-material <session_id> <material_path>
lecture-auto session refine-audio <session_id>
lecture-auto session refine-noise <session_id>
```

`import-material` accepts PDF, PPT, and PPTX files. PPT/PPTX files are converted to PDF and stored with the session.

### Capture

```bash
lecture-auto capture start <session_id>
lecture-auto capture stop <session_id>
```

Recording uses FFmpeg with AVFoundation on macOS, DirectShow on Windows, and PulseAudio or ALSA on Linux. System audio capture may require a loopback or monitor device.

### Transcription

```bash
lecture-auto transcription run <session_id>
```

Transcribes the session recording with the configured STT provider. If refined audio exists, it is used before the original recording.

### Summarize

```bash
lecture-auto summarize --id <session_id>
lecture-auto summarize --id <session_id> --preview
```

Generates structured lecture notes from the transcript. Template selection is deprecated; notes always use the `structured-notes` format.

### Library

```bash
lecture-auto library list
lecture-auto library search <query>
lecture-auto library open <session_id>
lecture-auto library open <session_id> --transcript
lecture-auto library open <session_id> --recordings
```

Use the library to browse sessions and generated artifacts.

## Providers

STT:

- `api`: Deepgram or an OpenAI-compatible provider
- `local`: local Whisper/faster-whisper

### Local STT hardware recommendations

These are **recommendations, not automatic model selection**. Automatic behavior
currently covers device/compute capability and smaller-batch retry on OOM.

| Hardware | Model | device / compute | Use |
| --- | --- | --- | --- |
| Low-end CPU, up to 8 GB RAM | `base` | `cpu / int8` | Fast draft; repetition checks required |
| General CPU, Apple Silicon | `small` | `cpu / int8` | Current default recommendation |
| NVIDIA 4–6 GB VRAM | `small` | `cuda / int8_float16` | Low-memory GPU |
| NVIDIA 8–12 GB VRAM | `medium` | `cuda / float16` | Balanced speed and accuracy |
| NVIDIA 16 GB+ VRAM | `large-v3` | `cuda / float16` | Accuracy first |
| AMD/Intel GPU | `small` | `cpu / int8` | GPU backend not currently supported |

Metal/MLX on Apple Silicon and Vulkan/OpenVINO on AMD/Intel are not implemented
yet. CUDA requires compatible cuBLAS/cuDNN libraries.

LLM:

- `gemini`: Google API; supports hosted Gemini and Gemma 4 models
- `ollama`: Ollama server; note generation goes through a JSON harness and is rendered as structured Markdown

Google API example:

```bash
LLM_PROVIDER=gemini LLM_MODEL=gemma-4-26b-a4b-it lecture-auto summarize --id week-01
```

Ollama example:

```bash
LLM_PROVIDER=ollama LLM_MODEL=gemma4:31b-cloud lecture-auto summarize --id week-01
```

## Useful Environment Variables

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

## JSON Output

Most commands support `--json`.

```bash
lecture-auto session detail week-01 --json
```

Response shape:

```json
{"command":"session detail","payload":{},"message":"Loaded details for session 'week-01'."}
```

## Notes

- Running `lecture-auto` with no subcommand opens the TUI.
- CLI commands are good for repeatable workflows and scripting.
- The TUI is usually easier for session-by-session work.
- Detailed setup, provider config, and troubleshooting live in [docs/setup.md](docs/setup.md).
