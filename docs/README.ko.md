# Lecture Auto

컴퓨터가 수업을 대신 듣게 해주는 CLI/TUI 도구.

녹음한 강의 오디오를 전사하고, 전사문을 다듬고, 구조화된 강의 노트까지 자동으로 만든다. 수업을 사람이 실시간으로 정리하는 대신, 프로그램이 `recording -> transcript -> structured notes` 흐름을 맡는다.

## What It Does

- 강의 세션 생성/관리
- 마이크 또는 시스템 오디오 녹음
- STT로 전사문 생성
- LLM으로 전사문 refinement
- LLM으로 구조화 노트 생성
- PDF/PPT/PPTX 수업 자료를 세션에 첨부
- 생성된 노트, 전사문, 녹음 파일 검색/열기
- CLI와 대화형 TUI 둘 다 지원

노트는 항상 `structured-notes` 형식으로 생성된다. Ollama 사용 시에는 모델이 Markdown을 직접 쓰지 않고, 섹션별 JSON을 만든 뒤 앱이 최종 Markdown을 렌더링한다.

## Quick Start

설치와 provider 설정 세부 내용은 [setup.ko.md](setup.ko.md)를 참고한다.

사전 요구사항: `pip install -e .`를 실행하기 전에 Rust를 설치해야 한다. 일부 Python dependency가 native extension을 빌드하면서 Rust toolchain을 요구한다. [rustup.rs](https://rustup.rs/)에서 설치한 뒤, `cargo`가 `PATH`에서 잡히도록 터미널을 다시 연다.

```bash
git clone https://github.com/fullsack73/auto_lecture_notes.git
cd auto_lecture_notes
pip install -e .
```

기본 설정:

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

TUI 실행:

```bash
lecture-auto
```

데스크톱 GUI 실행:

```bash
lecture-auto-gui
```

GUI는 기존 CLI/TUI와 같은 workspace와 세션 데이터를 사용한다. 첫 실행에서 저장 위치와 STT/LLM 방식을 선택하고, 이후 설정 화면에서 녹음 장치, API key, 로컬 Whisper 모델, Ollama 연결을 관리한다. API key는 운영체제 credential store에 저장되며 `config.json`에는 기록되지 않는다.

CLI로 한 세션 처리:

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

결과물은 workspace 아래에 저장된다.

```text
metadata/sessions.json
recordings/[course/]session-id.wav
transcripts/[course/]session-id-raw.md
transcripts/[course/]session-id-edited.md
materials/[course/]session-id.pdf
notes/[course/]session-id.md
```

## Main Workflow

1. 세션 생성
2. 수업 녹음
3. STT 실행
4. 전사문 refine
5. 노트 생성
6. library에서 결과 확인

전사문 refine는 현재 TUI의 Transcription 메뉴에서 실행한다. 노트 생성은 가장 좋은 전사문을 사용한다. edited transcript가 있으면 raw transcript보다 우선한다.

## Commands

### TUI

```bash
lecture-auto
```

가장 편한 진입점. 세션, 녹음, 전사, 전사문 refine, 노트 생성, library, 설정을 메뉴로 조작한다.

### Config

```bash
lecture-auto config set [OPTIONS]
lecture-auto config show
```

자주 쓰는 옵션:

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

`import-material`는 PDF, PPT, PPTX를 받는다. PPT/PPTX는 PDF로 변환해 세션 자료로 저장한다.

### Capture

```bash
lecture-auto capture start <session_id>
lecture-auto capture stop <session_id>
```

macOS FFmpeg/AVFoundation 기반 녹음. 시스템 오디오를 녹음하려면 BlackHole, Loopback, Soundflower 같은 loopback 장치가 필요할 수 있다.

### Transcription

```bash
lecture-auto transcription run <session_id>
```

설정된 STT provider로 녹음 파일을 전사한다. refined audio가 있으면 refined audio를 우선 사용한다.

### Summarize

```bash
lecture-auto summarize --id <session_id>
lecture-auto summarize --id <session_id> --preview
```

전사문에서 구조화 강의 노트를 만든다. 템플릿 선택은 deprecated이며, 항상 `structured-notes` 형식을 사용한다.

### Library

```bash
lecture-auto library list
lecture-auto library search <query>
lecture-auto library open <session_id>
lecture-auto library open <session_id> --transcript
lecture-auto library open <session_id> --recordings
```

저장된 세션과 생성물 탐색용.

## Providers

STT:

- `api`: Deepgram 또는 OpenAI-compatible provider
- `local`: local Whisper/faster-whisper

LLM:

- `gemini`: Google API. hosted Gemini와 Gemma 4 model 지원
- `ollama`: Ollama server. 노트 생성은 JSON harness를 거쳐 structured Markdown으로 렌더링

Google API 예시:

```bash
LLM_PROVIDER=gemini LLM_MODEL=gemma-4-26b-a4b-it lecture-auto summarize --id week-01
```

Ollama 예시:

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

대부분의 명령은 `--json`을 지원한다.

```bash
lecture-auto session detail week-01 --json
```

응답 형식:

```json
{"command":"session detail","payload":{},"message":"Loaded details for session 'week-01'."}
```

## Notes

- `lecture-auto`만 실행하면 TUI가 열린다.
- CLI는 반복 작업/스크립팅에 좋고, TUI는 세션별 작업에 편하다.
- 상세 설치, provider별 설정, 문제 해결은 [setup.ko.md](setup.ko.md)에 둔다.
