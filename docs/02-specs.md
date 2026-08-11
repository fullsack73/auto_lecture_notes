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
- **macOS 재설치**: 실행 중인 설치본은 녹음과 백그라운드 작업 보호를 위해 빌드 전에 감지하고 교체하지 않는다. 닫힌 기존 앱은 새 번들을 임시 경로에 복사하고 서명 및 GUI smoke launch를 검증한 뒤 교체한다. 복사나 검증에 실패하면 기존 설치본을 보존한다.
- **데스크톱 제공 방식**: 버전 태그는 Windows x86_64 installer, Linux x86_64 AppImage/portable archive와 SHA-256 목록을 GitHub Release에 게시한다. macOS 로컬 앱은 ad-hoc 서명이고 Windows/Linux 배포본도 코드 서명되지 않는다.

## B. 계층별 구현 규칙

### Entry points

`cli.py`, `tui.py`, `gui/`는 사용자 입력을 검증하고 서비스 메서드를 호출한 뒤 결과를 표현한다. 세션 상태 전이, 파일 경로 계산, provider 선택 같은 업무 규칙을 새로 복제하지 않는다.

GUI 설정 화면은 콤보·체크·숫자 변경을 짧게 debounce한 뒤 자동 저장하고 서비스를 갱신한다. 텍스트 설정은 편집 완료 시 자동 적용한다. 화면을 초기값으로 채우는 동안 발생한 signal은 저장을 유발하지 않으며, 별도의 하단 저장 버튼을 요구하지 않는다.

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
- local Whisper worker는 앱 프로세스와 분리된 장수 JSONL 프로세스로 실행한다.
  모델명/device/compute/thread별 인스턴스를 최대 2개 LRU로 재사용하며 기본 300초
  idle timeout, 명시적 unload, 취소·timeout·crash·앱 종료 시 프로세스 정리를 지원한다.
- CPU `cpu_threads=0`은 worker가 물리 core 수를 보수적으로 추정해 사용한다.
  `num_workers`와 함께 무제한 논리 core oversubscription을 만들지 않는다.
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
raw Markdown과 기존 CLI JSON의 기본 구조는 유지한다. `stt_quality.py`의
`ko-lecture-v1` 기준은 로컬 corpus의 false-positive를 줄이도록
`avg_logprob < -1.10`, `compression_ratio > 2.45`,
`no_speech_prob > 0.70`, 문자율 13자/초와 반복 탐지를 사용한다.

선택적 재전사는 의심 구간 앞뒤 기본 1.5초를 합치고 최대 8구간·총 120초까지만
beam 5 또는 명시한 강한 모델로 한 번 재처리한다. 결과는 timestamp midpoint로
1차 구간을 교체하고 정렬·중복 제거한다. 의심 segment 또는 시간이 60% 이상이면
무한 재시도 대신 `full_model_upgrade_recommended`를 기록한다. progress/cancel은
1차 segment generator iteration과 2차 window iteration 양쪽에서 유지한다.

local 성능 설정은 config JSON과 `STT_*` 환경변수, CLI/TUI/GUI에서 동일하게 다룬다.
기존 config에 필드가 없으면 CPU/int8/batch 1/beam 5/VAD off라는 종전 동작을 유지한다.
`cpu-fast`, `cpu-balanced`, `nvidia-balanced`, `quality-retry` 예시는
`stt_profiles.py`와 benchmark CLI가 같은 정의를 사용한다. Apple Metal/Core ML/MLX,
OpenVINO, Vulkan/ROCm, SenseVoice, Qwen3-ASR, Moonshine은 별도 model format·cache·
runtime·license를 가진 optional benchmark로 관리하며 기본 provider로 자동 채택하지 않는다.
graphics corpus A/B에서 1차 VAD 최소 무음 1,000ms가 2,000ms보다 누락과 반복을
줄였으므로 fast/balanced profile은 1,000ms를 사용한다. 품질 재전사는 앞뒤 문맥과
beam 5를 쓰므로 보수적인 2,000ms를 유지한다.

오디오 preflight는 FFprobe와 FFmpeg `volumedetect`/`silencedetect`로 duration,
sample rate, channel, mean/peak volume, clipping 위험과 silence 비율을 측정한다.
결과는 VAD, loudness normalization, capture level 점검의 benchmark 후보만 제안하며
원본을 덮어쓰거나 denoise/normalization을 자동 강제하지 않는다.
재사용이 2회 이상인 경우만 checksum 기반 16 kHz mono FLAC canonical cache 후보를
만들 수 있다. `loudnorm`은 실제 저음량·비 clipping, 80 Hz high-pass는 저주파 진동,
DeepFilterNet은 지속 잡음이 확인된 경우에만 A/B 후보가 된다. raw/normalized/denoised
각각의 CER·용어 recall을 비교해 개선이 없으면 raw를 선택한다. `dynaudnorm`은 기본 off다.

세션 제목·과목·PDF/PPTX의 고유명사, 영문 약어, 전문용어는 최대 64개·1,000자로
제한하고 중복 제거한 뒤 `hotwords`로 전달한다. 자료 용어는 철자 bias/검증에만 쓰며
실제 발화의 증거로 취급하지 않는다.

LLM refine는 raw sidecar의 timestamp, confidence, 1차/2차 ASR 정보를 선택적 evidence로
받는다. 수행 범위는 문장부호·띄어쓰기·문장 경계·명백한 용어 오타·무의미 반복 정리로
제한한다. 근거 없는 누락 문장·숫자·수식·고유명사를 생성하지 않고 충돌/저신뢰 구간은
`[불명확 mm:ss]`로 보존한다. 문장 경계 chunking을 사용하며 결과 옆 audit JSON에
checksum, 숫자/고유명사 변경과 unified diff를 기록한다.

benchmark 결과는 CER/WER, 용어 recall, 숫자·수식 recall, 누락률, 무음 hallucination,
반복, RTF, cold/warm wall time, worker peak RAM과 가능한 경우 NVIDIA VRAM,
모델/runtime/hardware/options/version을 기록한다. `--refined-dir`가 있으면 refine 전후
지표와 새 숫자·고유명사 변경도 분리해 계산한다. 개인 corpus 없는 CI는 합성/mock만 쓴다.

노트 생성은 edited transcript를 우선하고 없으면 raw transcript를 사용한다. 결과 포맷은 항상 `structured-notes`다.
최상위 Markdown 제목은 고정 문구가 아니라 transcript의 중심 주제를 요약한 `note_title`로 생성한다.
provider가 제목을 누락하거나 일반적인 제목을 반환하면 첫 번째 topic overview 항목을 호환 fallback으로 사용한다.

Ollama 노트 생성은 모델에 Markdown 작성을 직접 맡기지 않고 다음 경로를 따른다.

```text
transcript + materials context
  → note title + section JSON generation
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
python scripts/verify_lightweight_app.py --app <standalone-dir> --report <nuitka-report.xml>
lecture-auto --help
```

변경 범위가 작으면 관련 테스트를 먼저 실행하고, 최종적으로 전체 테스트를 실행한다. 실제 provider/장치가 필요한 검증은 통합 환경에서만 수행하고 기본 테스트를 외부 서비스에 의존시키지 않는다.
