# Agent Working Agreement

이 파일은 Lecture Auto 저장소에서 작업하는 개발자와 AI 에이전트가 공통으로 지킬 작업 기준이다. 제품 범위와 구현 규칙은 아래 문서가 기준이며, 이 파일은 실제 작업 절차와 안전 규칙을 요약한다.

## 반드시 읽기 (매 작업 전)

- `docs/01-folder-architecture.md`
- `docs/02-specs.md`
- `docs/03-product-plan.md`
- `docs/todo/00-todo-list.md`

요청과 관련된 TODO가 있으면 해당 `docs/todo/*.md`도 읽고, 이번 작업에 포함할지 사용자와 범위를 확인한다.

## 작업 시작 체크리스트

- 현재 변경사항과 작업 대상 모듈을 `git status` 및 코드로 확인했는가
- 작업이 Lecture Auto의 녹음 → 전사 → 전사문 정제 → 노트 생성 범위 안에 있는가
- `src/lecture_auto`의 책임 분리와 provider adapter 경계를 지키는가
- 비밀값, 녹음 파일, 사용자 workspace 산출물을 저장소에 추가하지 않는가
- CLI의 사람이 읽는 출력과 `--json` 응답 형식을 불필요하게 깨지 않는가
- 관련 테스트를 실행했는가
- 구조/스펙/제품 범위가 달라졌다면 `docs/01`, `docs/02`, `docs/03`을 갱신했는가

## 코드 변경 규칙

- 런타임 코드는 `src/lecture_auto` 아래에 두고, 테스트는 기능에 대응하는 `tests/test_*.py`에 둔다.
- CLI/TUI/GUI 진입점에서 핵심 업무 규칙을 직접 구현하지 않는다. `Application`, `SessionService`, `LibraryService`와 공용 runtime/adapter를 사용한다.
- 외부 STT/LLM provider는 adapter 경계 뒤에 둔다. provider별 SDK 예외와 응답 형식이 UI/서비스 계층으로 새지 않게 한다.
- 설정 파일에는 API key를 평문으로 쓰지 않는다. 비밀값은 `SecretStore`/OS credential store 흐름을 따른다.
- 구조화 노트는 `src/lecture_auto/templates/structured-notes.md`와 현재 JSON-to-Markdown 렌더링 규칙을 기준으로 한다.
- 하드웨어·네트워크·대형 모델 의존성이 있는 모듈은 가능한 한 지연 import하여 가벼운 import 경로를 보존한다.
- 기존 공용 명령, 경로, 상태 전이는 호환성을 우선한다. 변경이 필요하면 테스트와 사용자 문서를 함께 갱신한다.

## 검증 규칙

- 빠른 확인: `pytest -q`
- 앱 경량 import/패키징 관련 변경: `python scripts/verify_lightweight_app.py --app <standalone-dir> --report <nuitka-report.xml>`
- CLI 변경: 관련 `tests/test_*cli*.py`, `tests/test_cli_output*.py`와 `lecture-auto --help` 확인
- GUI 변경: 관련 smoke test를 실행하고 실제 장치/API 없이도 실패 원인이 분명한지 확인
- provider 연동은 자격 증명과 외부 서비스가 필요한 통합 테스트로 분리하며, 테스트에 실제 key를 넣지 않는다.

## 문서 업데이트 규칙

- 폴더 책임 변경은 `docs/01-folder-architecture.md`, 구현 규칙/의존성 변경은 `docs/02-specs.md`, 제품 범위/사용자 흐름 변경은 `docs/03-product-plan.md`에 반영한다.
- 중요한 변경은 `docs/reports/yymmdd-HHMM-NN-작업키워드.md`에 기록한다. 템플릿은 `docs/reports/_template.md`다.
- 지금 처리하지 못하지만 추후 해야 할 일은 `docs/todo/`에 기록하고 `docs/todo/00-todo-list.md`에 한 줄 요약을 추가한다.
- TODO를 완료하면 TODO 파일을 삭제하고 작업 기록을 남긴 뒤 목록에서도 제거한다.

## 우선순위

안전한 사용자 데이터 처리와 기존 워크플로 호환성을 최우선으로 한다. 이 파일과 01/02/03 문서가 충돌하면 01/02/03의 구체적인 규칙을 우선하며, 코드와 문서가 어긋난 경우 문서와 구현을 함께 바로잡는다.
