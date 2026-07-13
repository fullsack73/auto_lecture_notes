# Lecture Auto

[Korean documentation](docs/README.ko.md)

A CLI/TUI tool that lets your computer attend class for you.

Lecture Auto records lecture audio, transcribes it, refines the transcript, and generates structured study notes. Instead of taking notes manually in real time, you can hand off the `recording -> transcript -> structured notes` flow to the program.

## Project Documentation

The repository follows a docs-first working agreement based on [Austin's Docs Architecture](https://github.com/EunHyeokJung/austin-docs-architecture):

- [Agent working agreement](AGENTS.md)
- [Folder architecture](docs/01-folder-architecture.md)
- [Technical specs](docs/02-specs.md)
- [Product plan](docs/03-product-plan.md)
- [TODO index](docs/todo/00-todo-list.md)
- [Work reports](docs/reports/)

## What It Does

- Create and manage lecture sessions
- Record microphone or system audio
- Generate transcripts with STT
- Refine transcripts with an LLM
- Generate structured lecture notes with an LLM
- Attach PDF/PPT/PPTX course materials to sessions
- Search and open generated notes, transcripts, and recordings
- Use either CLI commands or the interactive TUI

Notes always use the `structured-notes` format. With Ollama, the model does not write Markdown directly; it generates section JSON, and the app renders the final Markdown.

## Quick Start

Detailed installation and provider setup live in [docs/setup.md](docs/setup.md). Korean setup docs are available at [docs/setup.ko.md](docs/setup.ko.md).

Prerequisite: install Rust before running `pip install -e .`. Some Python dependencies build native extensions and require the Rust toolchain. Install it from [rustup.rs](https://rustup.rs/), then restart your terminal so `cargo` is available on `PATH`.

```bash
git clone https://github.com/fullsack73/auto_lecture_notes.git
cd auto_lecture_notes
pip install -e .
```

Basic config:

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

Open the TUI:

```bash
lecture-auto
```

Run one session from the CLI:

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

Launch the desktop GUI:

```bash
lecture-auto-gui
```

The PySide6 desktop app shares its workspace and sessions with the CLI/TUI. It supports session management, capture, imports, audio cleanup, transcription, refinement, notes, library search, secure API-key storage, and local model management.

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

Recording uses FFmpeg/AVFoundation on macOS. System audio capture may require a loopback device such as BlackHole, Loopback, or Soundflower.

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
