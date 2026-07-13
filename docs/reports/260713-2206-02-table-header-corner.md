# 작업 기록 - macOS 표 헤더 모서리 수정

- 일시: 2026-07-13 22:06 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 버그 수정

## 요약

- macOS 앱의 세션/보관함 표 좌측 상단에 검은 모서리가 노출되는 UI 결함을 수정했다.
- 표 외곽의 둥근 테두리와 기존 레이아웃은 유지했다.

## 변경 범위

- PySide6 표 헤더의 첫 번째 섹션에 적용되던 개별 둥근 모서리 제거
- macOS Cocoa 렌더러에서 해당 스타일이 다시 추가되지 않도록 GUI smoke 회귀 테스트 추가
- 수정된 arm64 macOS 앱 재빌드 및 `/Applications/Lecture Auto.app` 재설치

## 주요 변경 파일

- `src/lecture_auto/gui/app.py`
- `tests/test_gui_smoke.py`

## 검증

- macOS Cocoa 렌더러로 수정 전 검은 모서리 재현 및 수정 후 이미지 비교
- GUI smoke 테스트: 9 passed
- 전체 테스트: 261 passed, 기존 pytest 반환값 경고 2건
- 설치 앱 smoke 실행: 종료 코드 0
- 경량 패키징 및 코드서명 검증 통과

## 리스크/이슈

- 없음. 공용 표 스타일의 문제 규칙만 제거했으므로 세션 관리와 강의 보관함 표에 동일하게 적용된다.

## 다음 작업

- 없음.

## 참고

- 사용자 제공 macOS 앱 화면 캡처
