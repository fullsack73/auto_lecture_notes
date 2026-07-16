# Setup

Lecture Auto를 실행하기 위한 설치와 provider 설정.

## Requirements

- Python 3.11+
- FFmpeg
- macOS 녹음 기능을 쓸 경우 AVFoundation 사용 가능 환경
- 시스템 오디오 녹음 시 loopback device
  - BlackHole
  - Loopback
  - Soundflower
- cloud STT 사용 시 STT API key
- hosted Gemini 또는 Gemma 4 model 사용 시 AI Studio의 Google API key
- Ollama 사용 시 Ollama server와 model

## Install

```bash
git clone https://github.com/fullsack73/lecture-auto.git
cd lecture-auto
pip install -e .
```

설치 확인:

```bash
lecture-auto --help
lecture_auto --help
```

source checkout에서 직접 실행:

```bash
PYTHONPATH=src python -m lecture_auto.cli --help
```

## macOS 데스크톱 앱 로컬 빌드

현재 GitHub Release로 미리 빌드된 앱을 제공하지 않는다. 다음 조건을 만족하는 Mac에서 사용자가 직접 빌드한다.

- Apple Silicon Mac (`uname -m` 결과가 `arm64`)
- Python 3.11 이상 ARM64 환경
- Xcode Command Line Tools
- Rust toolchain
- 빌드 파일을 위한 여유 디스크 공간과 FFmpeg 소스 다운로드용 네트워크

처음 한 번만 저장소를 clone한다.

```bash
git clone https://github.com/fullsack73/lecture-auto.git
cd lecture-auto
```

Command Line Tools와 Rust가 없다면 설치한다.

```bash
xcode-select --install
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

터미널을 다시 열고 프로젝트 루트에서 빌드한다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[build]'
scripts/build_macos_app.sh --install
```

성공하면 `/Applications/Lecture Auto.app`에 설치된다.

```bash
open "/Applications/Lecture Auto.app"
```

Applications에 설치하지 않고 빌드 결과만 확인하려면 `--install` 없이 실행한다.

```bash
scripts/build_macos_app.sh
open build/macos/LectureAuto.app
```

첫 FFmpeg/Nuitka 빌드는 시간이 걸릴 수 있다. 스크립트는 ARM64 FFmpeg/FFprobe를 소스에서 준비하고 앱에 포함하며, 결과 앱에 로컬 실행용 ad-hoc 서명을 적용한다. 이 앱은 Developer ID 서명이나 Apple 공증을 거친 공개 배포본이 아니므로 본인이 빌드한 Mac에서 사용하는 경로를 기준으로 한다.

빌드가 `This build script requires a native arm64 shell`로 실패하면 Intel Mac 또는 Rosetta shell이다. 다음 결과가 `arm64`인지 확인한다.

```bash
uname -m
python -c 'import platform; print(platform.machine())'
```

## Workspace

기본 workspace는 `~/.lecture_auto`다.

변경:

```bash
lecture-auto config set --workspace ./lecture_data
```

명령 1회만 override:

```bash
lecture-auto --workspace ./lecture_data session history
```

환경변수:

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

### OpenAI-compatible STT

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

Google API가 기본 LLM provider다. 호환성을 위해 provider 값은 `gemini`를 유지하며, hosted Gemini와 Gemma 4 model ID를 지원한다.

```bash
lecture-auto config set \
  --gemini-api-key "your-google-api-key" \
  --llm-model gemma-4-26b-a4b-it \
  --llm-thinking-level medium \
  --llm-language korean
```

지원 model preset:

```text
gemini-3.1-flash-lite
gemini-3-flash-preview
gemini-3.1-pro-preview
gemma-4-26b-a4b-it
gemma-4-31b-it
```

### Ollama

Ollama는 API key가 필요 없다. Ollama server가 떠 있고 model이 준비되어 있어야 한다.

```bash
LLM_PROVIDER=ollama LLM_MODEL=gemma4:31b-cloud lecture-auto summarize --id week-01
```

또는 TUI의 Config 메뉴에서 LLM provider를 `local`/`ollama`로 설정한다.

Ollama 노트 생성은 Markdown을 모델에게 직접 맡기지 않는다.

```text
transcript
-> section JSON generation
-> validation
-> optional repair
-> structured Markdown render
```

이 방식은 작은 모델이 Markdown 템플릿을 무시하는 문제를 줄인다.

## Capture Setup

마이크 녹음:

```bash
lecture-auto config set --capture-source microphone
```

시스템 오디오 녹음:

```bash
lecture-auto config set --capture-source system_audio
```

시스템 오디오는 macOS에 loopback device가 필요할 수 있다.

## Audio Refinement

STT 전처리에서 dynamic normalization:

```bash
lecture-auto config set --use-dynaudnorm
```

세션 녹음 파일 자체를 정규화:

```bash
lecture-auto session refine-audio week-01
```

DeepFilterNet noise reduction:

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

Google API key가 없거나 Ollama provider/model 설정이 맞지 않다.

Google API:

```bash
lecture-auto config set --gemini-api-key "your-google-api-key"
```

Ollama:

```bash
LLM_PROVIDER=ollama LLM_MODEL=<model> lecture-auto summarize --id <session_id>
```

### `Transcription config error`

STT mode/provider/API key를 확인한다.

```bash
lecture-auto config show
```

### Recording fails

FFmpeg 설치와 macOS audio permission을 확인한다.

```bash
ffmpeg -version
```

시스템 오디오 녹음이면 loopback device 설정도 확인한다.

### PPT/PPTX material import fails

PPT/PPTX 변환에는 LibreOffice가 필요할 수 있다. 안정성이 필요하면 PDF로 변환한 뒤 import하는 것이 가장 단순하다.
