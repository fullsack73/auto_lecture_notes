# 작업 기록 - 설정 자동 적용 및 컨트롤 정리

- 일시: 2026-08-11 16:52 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 버그 수정/GUI 개선

## 요약

- 설정 화면의 하단 저장 버튼을 제거하고 변경값을 자동 저장·적용하도록 변경했다.
- macOS에서 어색하게 표시되던 숫자 입력 화살표를 제거하고 직접 입력 및 키보드 방향키 조작을 유지했다.
- 콤보 팝업 배경, 보관함 폴더 버튼 간격, 녹음 장치 선택 행을 기존 디자인 시스템 안에서 정리했다.

## 변경 범위

- 콤보·체크·숫자 설정 350ms debounce 자동 적용
- 텍스트 설정 편집 완료 시 자동 적용
- 초기 화면 refresh signal의 불필요한 저장 방지
- 밝은 콤보 팝업 viewport와 선택/hover 상태
- 숫자 입력 스핀 버튼 제거
- 폴더 버튼 12px 간격과 녹음 장치 선택/새로고침 비율 조정

## 주요 변경 파일

- `src/lecture_auto/gui/app.py`
- `tests/test_gui_smoke.py`
- `docs/02-specs.md`
- `docs/03-product-plan.md`

## 검증

- GUI, 설정 저장소, 경량 import 관련 테스트: 28 passed
- 외부 Ollama 실서비스 테스트를 제외한 전체 테스트: 331 passed, 1 skipped
- 설정 화면 1280×820 상단/중간 및 콤보 팝업 offscreen 렌더 육안 검수
- Python 문법 검사 및 `git diff --check` 통과
- Python 3.11 arm64 독립 앱 빌드 및 패키지 smoke test 통과
- 새 빌드의 deep code-sign 검증 통과
- 실행 중이던 기존 앱을 정상 종료한 뒤 안전 교체 설치, 설치본 재실행 확인

## 리스크/이슈

- 텍스트 입력은 타이핑 중이 아니라 포커스를 옮기거나 Enter를 눌러 편집을 마쳤을 때 적용한다.
- 숫자 입력은 버튼 대신 직접 입력과 키보드 위/아래 방향키를 사용한다.

## 다음 작업

- 없음.

## 참고

- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`
