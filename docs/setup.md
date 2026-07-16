# Setup

[Korean documentation](setup.ko.md)

Installation and provider setup for Lecture Auto.

## Requirements

- Python 3.11+
- FFmpeg
- macOS with AVFoundation support for built-in recording
- A loopback device for system-audio recording, such as:
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

## Build the macOS Desktop App Locally

Prebuilt desktop binaries are not currently published through GitHub Releases. Users build the app on a Mac that meets these requirements:

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
