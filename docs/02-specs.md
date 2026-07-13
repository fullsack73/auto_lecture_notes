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
- **플랫폼**: macOS 녹음/앱 배포를 우선 지원하며 Windows 배포 설정도 유지한다.

## B. 계층별 구현 규칙

### Entry points

`cli.py`, `tui.py`, `gui/`는 사용자 입력을 검증하고 서비스 메서드를 호출한 뒤 결과를 표현한다. 세션 상태 전이, 파일 경로 계산, provider 선택 같은 업무 규칙을 새로 복제하지 않는다.

### Application and services

`application.py`가 설정과 의존성을 조립한다. `SessionService`는 세션 생성/수정/삭제, 녹음, 자료 import, 전사, 정제, 요약의 orchestration과 상태 규칙을 소유한다. `LibraryService`는 생성물 탐색과 열기를 소유한다.

### Runtime and adapters

- STT는 API(`Deepgram`, OpenAI-compatible)와 local(`faster-whisper`)을 adapter로 분리한다.
- LLM은 `gemini`와 `ollama` provider를 공통 `LLMProviderAdapter` 경계로 제공한다.
- 녹음은 FFmpeg/AVFoundation 등 플랫폼 실행 세부사항을 `capture_runtime.py` 안에 둔다.
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
  → (선택) LLM refinement
  → edited transcript
```

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
