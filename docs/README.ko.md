# Lecture Auto

[English documentation](../README.md)

컴퓨터가 수업을 대신 듣게 해주는 데스크톱 GUI, CLI, TUI 애플리케이션.

녹음한 강의 오디오를 전사하고, 전사문을 다듬고, 구조화된 강의 노트까지 자동으로 만든다. 수업을 사람이 실시간으로 정리하는 대신, 프로그램이 `recording -> transcript -> structured notes` 흐름을 맡는다.

## What It Does

- 강의 세션 생성/관리
- 마이크 또는 시스템 오디오 녹음
- STT로 전사문 생성
- LLM으로 전사문 refinement
- LLM으로 구조화 노트 생성
- PDF/PPT/PPTX 수업 자료를 세션에 첨부
- 생성된 노트, 전사문, 녹음 파일 검색/열기
- 데스크톱 GUI, CLI 명령, 대화형 TUI 지원

노트는 항상 `structured-notes` 형식으로 생성된다. Ollama 사용 시에는 모델이 Markdown을 직접 쓰지 않고, 섹션별 JSON을 만든 뒤 앱이 최종 Markdown을 렌더링한다.

## How to Install

설치와 provider 설정 세부 내용은 [setup.ko.md](setup.ko.md)를 참고한다. 영문 설치 문서는 [setup.md](setup.md)에서 볼 수 있다.

먼저 저장소를 clone한다.

```bash
git clone https://github.com/fullsack73/lecture-auto.git
cd lecture-auto
```

### 1. 데스크톱 앱 로컬 빌드 및 실행

빌드 전에 Python 3.11 이상과 Rust toolchain을 설치한다. 데스크톱 앱은 교차 컴파일하지 않고 실행할 운영체제에서 네이티브로 빌드한다.

#### macOS (Apple Silicon)

Xcode Command Line Tools를 먼저 설치한 뒤 앱을 빌드하고 설치한다.

```bash
xcode-select --install  # Command Line Tools가 이미 있으면 생략
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[build]'
scripts/build_macos_app.sh --install
open "/Applications/Lecture Auto.app"
```

빌드는 ARM64 FFmpeg/FFprobe를 앱에 포함하고 로컬 실행용 ad-hoc 서명을 적용한다. Developer ID 서명이나 Apple 공증을 거친 공개 배포본은 아니다. 요구사항과 문제 해결은 [macOS 빌드 가이드](setup.ko.md#macos-데스크톱-앱-로컬-빌드)를 참고한다.

#### Windows (x86_64)

PowerShell에서 빌드 환경을 만들고 네이티브 빌드를 실행한다.

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
./scripts/build_windows_app.ps1
./build/windows/LectureAuto.dist/LectureAuto.exe
```

Inno Setup 6가 설치되어 있으면 `-Installer`를 추가해 `dist-installer/LectureAuto-Setup.exe`도 만들 수 있다. 네이티브 컴파일러 요구사항은 [Windows 빌드 가이드](setup.ko.md#windows-데스크톱-앱-로컬-빌드)를 참고한다.

#### Linux (x86_64 또는 ARM64)

[Linux 빌드 가이드](setup.ko.md#linux-데스크톱-앱-로컬-빌드)에 나온 compiler, `patchelf`, 배포판 패키지를 설치한 뒤 실행한다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[build]'
bash scripts/build_linux_app.sh
build/linux/LectureAuto.dist/LectureAuto
```

`--appimage`를 지정하면 portable tar archive와 함께 AppImage도 만든다. Windows/Linux 빌드는 checksum으로 검증한 LGPL FFmpeg/FFprobe와 라이선스 고지를 포함한다.

PySide6 데스크톱 앱은 CLI/TUI와 같은 workspace와 세션 데이터를 사용한다. 세션 관리, 녹음, 자료 import, 오디오 정제, 전사, 전사문 정제, 노트 생성, library 검색, 안전한 API key 저장, 로컬 모델 관리를 지원한다.

### 2. CLI/TUI 설치 및 사용

source checkout에서 설치하기 전에 Python 3.11 이상, FFmpeg, Rust를 설치한다. 일부 Python dependency가 native extension을 빌드하면서 Rust toolchain을 요구한다. Rust는 [rustup.rs](https://rustup.rs/)에서 설치하고, `cargo`가 `PATH`에서 잡히도록 터미널을 다시 연다.

```bash
python -m pip install -e .
```

workspace와 provider를 설정한다.

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

대화형 TUI를 연다.

```bash
lecture-auto
```

CLI로 전체 세션을 처리한다.

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

녹음은 macOS에서 FFmpeg/AVFoundation, Windows에서 DirectShow, Linux에서 PulseAudio 또는 ALSA를 사용한다. 시스템 오디오 녹음에는 loopback 또는 monitor 장치가 필요할 수 있다.

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
