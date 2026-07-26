# 1) 폴더 아키텍처

이 문서는 Lecture Auto 저장소의 실제 폴더 책임과 의존성 방향을 정의한다. 프로젝트는 웹 모노레포나 FSD 구조가 아닌 Python 단일 패키지 구조를 사용한다.

## A. 저장소 최상위 구조

```text
.
├─ AGENTS.md                         # AI/개발자 작업 합의서
├─ README.md                         # 프로젝트 개요와 빠른 시작
├─ docs/
│  ├─ README.ko.md, setup*.md        # 사용자용 제품/설치 문서
│  ├─ 01-folder-architecture.md      # 저장소 구조와 책임
│  ├─ 02-specs.md                    # 기술 스펙과 구현 규칙
│  ├─ 03-product-plan.md             # 제품 범위와 사용자 흐름
│  ├─ reports/                        # 중요한 완료 작업 기록
│  │  └─ _template.md
│  └─ todo/                           # 보류/차단된 후속 작업
│     ├─ 00-todo-list.md
│     └─ _template.md
├─ src/lecture_auto/                 # 배포되는 Python 패키지
├─ tests/                             # pytest 테스트
├─ scripts/                           # 빌드와 경량 검증 스크립트
├─ deployment/                        # Windows/macOS/Linux 배포 보조 파일
├─ .github/workflows/                 # CI 및 데스크톱 빌드
└─ pyproject.toml                     # 패키지, 의존성, entry point 설정
```

`build/`, `.venv/`, `__pycache__/`, `.pytest_cache/`와 사용자 workspace 산출물은 개발/실행 결과이며 소스 구조의 일부로 취급하지 않는다.

## B. Python 패키지 구조

```text
src/lecture_auto/
├─ cli.py                       # Typer CLI entry point와 명령 wiring
├─ tui.py                       # questionary 기반 대화형 TUI
├─ gui/
│  ├─ app.py                    # PySide6 GUI entry point
│  ├─ LectureAuto.py            # GUI 화면/컨트롤러
│  ├─ jobs.py                   # GUI 백그라운드 작업
│  ├─ i18n.py                   # GUI 번역
│  └─ assets/                   # 앱 아이콘 등 패키지 리소스
├─ application.py              # AppConfig, 설정 저장소, 서비스 조립, 비밀값 저장
├─ session_service.py           # 세션 도메인 규칙과 녹음/전사/노트 orchestration
├─ session_metadata_store.py    # sessions.json 영속화와 메타데이터 접근
├─ library_service.py            # 세션 산출물 검색/열기/목록
├─ capture_runtime.py            # FFmpeg/플랫폼별 녹음 실행
├─ audio_amplifier.py            # 오디오 정규화/증폭
├─ audio_preflight.py            # loudness/clipping/silence 기반 STT 입력 진단
├─ stt_config.py, stt_runtime.py # STT 설정과 provider 실행 경로
├─ stt_quality.py                # confidence/반복 기반 의심 구간 판정
├─ stt_profiles.py               # 하드웨어 profile과 backend 평가 registry
├─ stt_glossary.py               # 세션/자료 기반 제한된 STT 용어 추출
├─ stt_audio_policy.py           # 조건부 오디오 후보·canonical cache 정책
├─ stt_refinement.py             # refine evidence/chunk/audit 규칙
├─ deepgram_adapter.py           # Deepgram adapter
├─ whisper_adapter.py            # local Whisper/faster-whisper adapter
├─ llm_config.py, llm_adapter.py # LLM 설정, 전사 정제, 노트 생성
├─ gemini_addon*.py              # Gemini 보조 worker 경로
├─ local_runtime.py              # Ollama/local runtime 관리
├─ local_ai_worker.py            # local AI worker 실행
├─ local_worker_adapter.py       # local worker adapter
├─ model_manager.py              # local 모델 관리
├─ document_converter.py         # PDF/PPT/PPTX 자료 변환
├─ tasking.py                    # 작업 실행/상태 보조
├─ cli_output.py                 # 텍스트/JSON CLI 출력 포맷
└─ templates/structured-notes.md # 기본 구조화 노트 형식
```

## C. 의존성 방향

```text
CLI / TUI / GUI
        │
        ▼
Application 조립 ──► SessionService / LibraryService
        │                         │
        ├─ Config/SecretStore     ├─ MetadataStore
        ├─ STT runtime/adapters   ├─ Capture runtime
        └─ LLM runtime/adapters   └─ Document converter
```

- 진입점(`cli.py`, `tui.py`, `gui/`)은 입력/표시와 작업 연결을 담당한다.
- 도메인 서비스는 UI toolkit이나 provider SDK를 직접 노출하지 않는다.
- provider adapter는 공용 protocol/서비스 경계 뒤에 있으며 다른 provider의 구현을 import하지 않는다.
- `cli_output.py`는 서비스 결과를 표현 형식으로 변환하는 곳이다. 서비스가 CLI 문자열을 직접 만들지 않는다.
- `tests/`는 공개 동작을 기준으로 서비스, runtime, adapter, 출력, GUI smoke를 각각 검증한다.

## D. 실행 산출물 구조

기본 workspace는 `~/.lecture_auto`이며 설정으로 변경할 수 있다.

```text
workspace/
├─ metadata/sessions.json
├─ recordings/[course/]session-id.wav|mp3
├─ transcripts/[course/]session-id-raw.md
├─ transcripts/[course/]session-id-raw.stt.json
├─ transcripts/[course/]session-id-edited.md
├─ transcripts/[course/]session-id-edited.audit.json
├─ materials/[course/]session-id.pdf
└─ notes/[course/]session-id.md
```

workspace 파일은 사용자 데이터이므로 저장소에 커밋하지 않는다. 코드에는 절대 경로를 하드코딩하지 않고 `AppConfig.workspace`와 path helper를 사용한다.

`session-id-raw.stt.json`은 raw Markdown 형식을 바꾸지 않고 provider/runtime 설정,
segment timestamp, confidence, 선택적 word timestamp를 보존하는 versioned sidecar다.
`session-id-edited.audit.json`은 원문/수정문 checksum, 숫자와 영문 고유명사 변경,
통합 diff를 보존하며 기존 transcript 파일 형식에는 영향을 주지 않는다.
개발용 `scripts/benchmark_local_stt.py`는 저장소 밖 또는 ignore 대상 녹음 corpus를 읽고
`build/stt-benchmarks/`에만 비교 결과를 만든다.
