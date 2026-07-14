# 작업 기록 - 설정 보조 버튼 표면 보정

- 일시: 2026-07-14 15:10 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: GUI 리팩터/시각 보정

## 요약

- 설정의 `설치 복구`, `외부 Python`, `Runtime 제거`, `모델 삭제`가 패널 안에서 떠 보이던 문제를 수정했다.
- 텍스트 링크 스타일을 작은 외곽선 버튼으로 바꾸고 같은 행의 폭과 높이를 정렬했다.

## 변경 범위

- 보조 버튼에 중립 배경, 1px 테두리, 6px radius와 hover 상태 적용
- 삭제 버튼에 옅은 위험 배경과 붉은 테두리를 적용해 기능 의미를 유지
- Runtime 유지보수 버튼 3개를 같은 폭으로 정렬
- Whisper 모델 받기/삭제 버튼을 같은 폭으로 정렬
- `redesign-existing-projects` 지침에 따라 기존 작업 위계와 콜백은 유지하고 표면과 정렬만 보정

## 주요 변경 파일

- `src/lecture_auto/gui/app.py`
- `tests/test_gui_smoke.py`

## 검증

- `pytest -q tests/test_gui_smoke.py`: 14 passed
- `pytest -q`: 267 passed, 기존 Ollama 통합 테스트 경고 2건
- Runtime/모델 패널 기본 창 크기 시각 검수
- `scripts/build_macos_app.sh --install`: 성공
- 설치 앱 smoke 실행: 성공
- `codesign --verify --deep --strict`: 성공
- `scripts/verify_lightweight_app.py`: 성공

## 리스크/이슈

- 기능 및 확인 대화상자 동작은 변경하지 않았다.

## 다음 작업

- 없음

## 참고

- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`
