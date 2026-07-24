# 2) 기술 스펙과 구현 규칙

이 문서는 현재 Lecture Auto가 실제로 사용하는 런타임, 의존성, 데이터 경계와 변경 규칙을 정의한다.

## A. Runtime / packaging

- **언어**: Python 3.11+
- **빌드**: setuptools, `pyproject.toml`
- **배포 entry point**: `lecture-auto`, `lecture_auto`, `lecture-auto-gui`
- **CLI**: Typer
- **TUI**: questionary
- **GUI**: PySide6
- **테스트**: pytest, 선택적으로 pytest-qt
- **플랫폼**: macOS ARM64, Windows x86_64, Linux x86_64/ARM64의 네이티브 GUI 빌드를 지원한다. 교차 컴파일은 지원하지 않는다.
- **macOS 미디어 도구**: 배포 앱은 ARM64 FFmpeg/FFprobe를 `Contents/MacOS/bin`에 포함한다. 빌드 스크립트는 고정된 소스와 checksum으로 GPL/nonfree 기능을 끈 바이너리를 준비하고 AVFoundation, MP3, 외부 Homebrew dylib 비의존성을 검증한다.
- **Windows/Linux 미디어 도구**: 월말 보존되는 고정 BtbN LGPL 빌드와 SHA-256을 사용한다. Windows는 DirectShow, Linux는 PulseAudio 또는 ALSA 입력과 MP3 지원을 검증하며 FFmpeg 라이선스와 소스 정보를 앱에 포함한다.
- **데스크톱 패키징**: 모든 플랫폼은 Nuitka standalone 빌드에서 구조화 노트 템플릿, add-on worker, `uv`, FFmpeg/FFprobe를 같은 상대 경로로 포함한다. Windows는 Inno Setup installer를, Linux는 tar.gz와 선택적 AppImage를 생성한다.
- **데스크톱 제공 방식**: 버전 태그는 Windows x86_64 installer, Linux x86_64 AppImage/portable archive와 SHA-256 목록을 GitHub Release에 게시한다. macOS 로컬 앱은 ad-hoc 서명이고 Windows/Linux 배포본도 코드 서명되지 않는다.

## B. 계층별 구현 규칙

### Entry points

`cli.py`, `tui.py`, `gui/`는 사용자 입력을 검증하고 서비스 메서드를 호출한 뒤 결과를 표현한다. 세션 상태 전이, 파일 경로 계산, provider 선택 같은 업무 규칙을 새로 복제하지 않는다.

### Application and services

`application.py`가 설정과 의존성을 조립한다. `SessionService`는 세션 생성/수정/삭제, 녹음, 자료 import, 전사, 정제, 요약의 orchestration과 상태 규칙을 소유한다. `LibraryService`는 생성물 탐색과 열기를 소유한다.

### Runtime and adapters

- STT는 API(`Deepgram`, OpenAI-compatible)와 local(`faster-whisper`)을 adapter로 분리한다.
- local faster-whisper의 device/compute/batch/VAD/beam/thread 설정은 `STTConfig`와
  worker request를 거친다. 앱 프로세스는 CTranslate2/faster-whisper를 직접 import하지 않는다.
- `device=auto`, `compute_type=auto`는 worker가 실제 CTranslate2 capability를 조회해
  선택한다. CUDA 초기화 실패는 CPU로 숨겨서 fallback하지 않고 해결 방법과 함께 실패시킨다.
- batch inference는 VAD가 켜진 경우만 허용한다. 메모리 부족이면 batch를 절반씩 줄여
  재시도하고 실제 batch와 재시도 횟수를 결과 metadata에 기록한다.
- LLM은 `gemini`와 `ollama` provider를 공통 `LLMProviderAdapter` 경계로 제공한다.
- 녹음은 FFmpeg/AVFoundation 등 플랫폼 실행 세부사항을 `capture_runtime.py` 안에 둔다. 런타임은 앱에 포함된 `bin/ffmpeg`와 `bin/ffprobe`를 시스템 `PATH`보다 우선한다.
- 외부 SDK import는 adapter/runtime 내부에서 지연 import할 수 있으며, 가벼운 명령과 테스트 import를 불필요하게 막지 않는다.
- provider 예외는 서비스/CLI가 처리할 수 있는 프로젝트 예외로 변환한다.

## C. 데이터와 보안

- 설정 일반값은 JSON config에 저장한다.
- STT/LLM API key는 `SecretStore`를 통해 OS credential store에 저장하며 `config.json`에 평문으로 기록하지 않는다.
- `LECTURE_AUTO_*`, `STT_*`, `LLM_*`, `GEMINI_API_KEY` 환경변수는 명시된 설정 override 경로로만 사용한다.
- 사용자 workspace 경로는 `Path.expanduser().resolve()`를 거쳐 다룬다.
- 테스트에는 실제 API key, 강의 녹음, 개인 자료를 사용하지 않는다.

## D. STT/LLM 처리 규칙

STT 처리 순서는 기본적으로 다음과 같다.

```text
recording
  → (선택) volume/noise refinement
  → STT adapter
  → raw transcript
  → raw STT metadata sidecar
  → (선택) LLM refinement
  → edited transcript
```

local STT는 raw transcript와 별도로 `*-raw.stt.json` sidecar를 쓴다. schema version,
provider/language/runtime, segment 시작·종료, `avg_logprob`, `compression_ratio`,
`no_speech_prob`, temperature와 선택적 word probability/timestamp를 포함한다.
raw Markdown과 기존 CLI JSON의 기본 구조는 유지한다. `stt_quality.py`는 초기 기준
`avg_logprob < -1.0`, `compression_ratio > 2.4`, `no_speech_prob > 0.6` 및
비정상 문자율/반복을 의심 구간으로 표시한다. 이 기준은 corpus benchmark로 보정한다.

local 성능 설정은 config JSON과 `STT_*` 환경변수, CLI/TUI/GUI에서 동일하게 다룬다.
기존 config에 필드가 없으면 CPU/int8/batch 1/beam 5/VAD off라는 종전 동작을 유지한다.

오디오 preflight는 FFprobe와 FFmpeg `volumedetect`/`silencedetect`로 duration,
sample rate, channel, mean/peak volume, clipping 위험과 silence 비율을 측정한다.
결과는 VAD, loudness normalization, capture level 점검의 benchmark 후보만 제안하며
원본을 덮어쓰거나 denoise/normalization을 자동 강제하지 않는다.

노트 생성은 edited transcript를 우선하고 없으면 raw transcript를 사용한다. 결과 포맷은 항상 `structured-notes`다.

Ollama 노트 생성은 모델에 Markdown 작성을 직접 맡기지 않고 다음 경로를 따른다.

```text
transcript + materials context
  → section JSON generation
  → validation / optional repair
  → application Markdown render
```

이 규칙을 바꾸면 `llm_adapter.py`, 관련 테스트, `src/lecture_auto/templates/structured-notes.md`, 사용자 문서를 함께 검토한다.

## E. 공개 인터페이스 호환성

- 기존 CLI 명령 이름과 주요 인자(`session`, `capture`, `transcription`, `summarize`, `library`, `config`)를 유지한다.
- 대부분의 명령은 사람이 읽는 기본 출력과 `--json` 출력을 제공한다.
- JSON 결과는 `command`, `payload`, `message` 구조를 기본으로 하며, 변경 시 출력 테스트를 먼저 갱신한다.
- 세션 상태와 workspace 파일명 규칙은 기존 데이터가 계속 열리도록 하위 호환성을 우선한다.

## F. 검증

```bash
pytest -q
python scripts/verify_lightweight_app.py
lecture-auto --help
```

변경 범위가 작으면 관련 테스트를 먼저 실행하고, 최종적으로 전체 테스트를 실행한다. 실제 provider/장치가 필요한 검증은 통합 환경에서만 수행하고 기본 테스트를 외부 서비스에 의존시키지 않는다.
