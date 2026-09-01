# 작업 기록 - 실시간 녹음 입력 레벨

- 일시: 2026-09-01 18:28 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 기능 추가

## 요약

- 데스크톱 GUI에서 녹음 중인 입력의 peak dBFS와 레벨 미터를 실시간 표시한다.

## 변경 범위

- FFmpeg 녹음 스트림의 `astats` peak metadata 수집
- `SessionService`를 통한 최신 입력 레벨 조회
- 세션 관리 화면의 녹음 중 전용 입력 미터

## 주요 변경 파일

- `src/lecture_auto/capture_runtime.py`
- `src/lecture_auto/session_service.py`
- `src/lecture_auto/gui/app.py`
- `tests/test_capture_cross_platform.py`
- `tests/test_gui_smoke.py`

## 검증

- `.venv/bin/pytest -q tests/test_capture_cross_platform.py tests/test_gui_smoke.py`
- `PYTHONPATH=. .venv/bin/pytest -q` (342 passed, 1 skipped)
- FFmpeg synthetic sine 입력으로 `lavfi.astats.Overall.Peak_level` 출력 확인

## 리스크/이슈

- 실제 표시값은 선택한 입력 장치와 운영체제 권한에 따라 달라진다.

## 다음 작업

- 없음

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
