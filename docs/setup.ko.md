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

## Windows/Linux 데스크톱 앱 설치

[최신 GitHub Release](https://github.com/fullsack73/lecture-auto/releases/latest)에서 운영체제에 맞는 64비트 설치 파일을 받는다. FFmpeg와 FFprobe가 포함되어 있다.

- Windows: `LectureAuto-Setup.exe`를 실행한다. 코드 서명이 없어 SmartScreen 확인이 표시될 수 있다.
- Linux AppImage: `chmod +x LectureAuto-linux-x86_64.AppImage` 실행 후 파일을 연다.
- Linux portable archive: `LectureAuto-linux-x86_64.tar.gz`를 푼 뒤 `LectureAuto.dist/LectureAuto`를 실행한다.

설치 후 앱 안에서 API key와 workspace를 설정한다. Windows/Linux 패키지는 버전 태그에서 자동 빌드되며 같은 Release의 `SHA256SUMS.txt`에서 SHA-256 값을 확인할 수 있다.

## macOS 데스크톱 앱 로컬 빌드

GitHub Release에서는 Windows와 Linux 설치 파일을 제공한다. macOS는 다음 조건을 만족하는 Mac에서 사용자가 직접 빌드한다.

- Apple Silicon Mac (`uname -m` 결과가 `arm64`)
- ARM64 Python 3.11 환경(3.12 이상이 아닌 정확히 3.11)
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

기존 설치본을 업데이트할 때는 먼저 Lecture Auto를 종료한다. 녹음 또는 백그라운드 작업을 보호하기 위해 실행 중인 앱은 설치 스크립트가 강제로 종료하거나 교체하지 않는다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[build]'
scripts/build_macos_app.sh --install
```

성공하면 실행 smoke test와 서명 검증을 통과한 앱이 `/Applications/Lecture Auto.app`에 설치된다. 복사나 검증이 실패하면 기존 설치본은 유지된다.

macOS 패키지는 Python 3.11에서만 검증된다. 스크립트가 다른 Python을 감지하면 빌드 파일이나 기존 설치본을 건드리기 전에 종료한다. `python3.11` 명령이 없다면 Python 3.11을 먼저 설치한다.

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

## Windows 데스크톱 앱 로컬 빌드

x86_64 Windows와 Python 3.11 이상을 지원한다. Nuitka가 안내하는 C/C++ build tools를 설치하고, installer가 필요하면 Inno Setup 6도 설치한다. 저장소 루트의 PowerShell에서 실행한다.

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
./scripts/build_windows_app.ps1
./build/windows/LectureAuto.dist/LectureAuto.exe
```

installer 생성:

```powershell
./scripts/build_windows_app.ps1 -Installer
./dist-installer/LectureAuto-Setup.exe
```

스크립트는 고정된 x86_64 LGPL FFmpeg 빌드를 다운로드하여 SHA-256, DirectShow, MP3 지원을 검증하고 FFmpeg 라이선스와 소스 고지를 포함한다. 패키징된 GUI smoke 실행까지 통과해야 빌드가 성공한다.

## Linux 데스크톱 앱 로컬 빌드

x86_64와 ARM64 Linux, Python 3.11 이상을 지원한다. Debian/Ubuntu에서는 다음과 같이 준비한다.

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

일반 빌드도 `dist-release/LectureAuto-linux-<arch>.tar.gz`를 만든다. AppImage가 필요하면 실행한다.

```bash
bash scripts/build_linux_app.sh --appimage
```

Linux 빌드는 고정된 LGPL FFmpeg/FFprobe를 포함하고 PulseAudio 또는 ALSA 입력, MP3, 라이선스 고지와 headless GUI smoke 실행을 확인한다. AppImage는 checksum으로 고정한 `linuxdeploy` asset으로 만든다.

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

CPU 빠른 profile 예시:

```bash
lecture-auto config set \
  --stt-mode local \
  --stt-local-model small \
  --stt-device cpu \
  --stt-compute-type int8 \
  --stt-batch-size 4 \
  --stt-beam-size 1 \
  --stt-temperature 0 \
  --stt-vad-filter \
  --stt-vad-min-silence-ms 1000 \
  --no-stt-condition-on-previous-text
```

`batch-size > 1`은 VAD와 함께 사용해야 한다. 메모리 부족 시 worker는 batch를
절반씩 줄여 재시도하며, 실제 설정은 전사 결과의 `local_runtime`과
`*-raw.stt.json` sidecar에 기록된다. 작은 모델의 batch 전사에서 반복이 감지되면
`small` 이상 모델을 쓰거나 batch 1로 비교한다.

저신뢰 구간만 최대 8개·총 120초 재전사하는 기본 안전장치는 다음처럼 조정할 수 있다.

```bash
lecture-auto config set \
  --stt-quality-retry \
  --stt-quality-retry-model large-v3 \
  --stt-quality-retry-beam-size 5 \
  --stt-quality-retry-context-seconds 1.5 \
  --stt-quality-retry-max-windows 8 \
  --stt-quality-retry-max-seconds 120
```

세션 제목·과목·PDF/PPTX 자료의 용어는 길이/개수 제한 후 hotword로 합쳐지며,
자료에만 있는 내용을 transcript 사실로 삽입하지 않는다. worker 모델 cache의 기본
idle timeout은 300초이고 `LECTURE_AUTO_WARM_WORKER_IDLE_SECONDS`로 바꿀 수 있다.

개발 benchmark:

```bash
python scripts/benchmark_local_stt.py --list-profiles
python scripts/benchmark_local_stt.py --list-backends
python scripts/benchmark_local_stt.py \
  --profile cpu-balanced --pair graphics --runs 2 --audio-preflight
```

`--runs 2` 이상이면 같은 worker/model의 cold/warm 시간을 분리한다.
`--refined-dir <dir>`은 `refined-<pair>.md`를 찾아 refine 전후 정확도와 숫자·
고유명사 변경을 평가한다. 결과와 hypothesis는 `build/stt-benchmarks/`에만 남는다.

NVIDIA profile은 `--stt-device cuda --stt-compute-type float16`을 쓸 수 있다.
CTranslate2와 호환되는 CUDA 12 cuBLAS/cuDNN DLL이 없으면 명시적으로 실패한다.
이때 `--stt-device cpu --stt-compute-type int8`로 바꾸거나 CUDA runtime을 설치한다.

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
STT_LOCAL_DEVICE
STT_COMPUTE_TYPE
STT_BATCH_SIZE
STT_BEAM_SIZE
STT_TEMPERATURE
STT_VAD_FILTER
STT_VAD_MIN_SILENCE_MS
STT_CONDITION_ON_PREVIOUS_TEXT
STT_WORD_TIMESTAMPS
STT_HOTWORDS
STT_CPU_THREADS
STT_NUM_WORKERS
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
