# 작업 기록 - provider별 설정 입력 비활성화

- 일시: 2026-07-14 15:20 (Asia/Seoul)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: UX 개선/버그 수정

## 요약

- 현재 선택한 STT 및 LLM 방식과 무관한 설정 입력을 회색 비활성 상태로 표시하도록 개선했다.
- 비활성화 시 저장된 값과 사용자가 입력한 값은 유지하며 provider를 다시 선택하면 즉시 편집할 수 있다.

## 변경 범위

- 로컬 Whisper 선택 시 STT API provider와 API key를 비활성화하고 Whisper 모델을 활성화한다.
- API STT 선택 시 Whisper 모델을 비활성화하고 API provider와 API key를 활성화한다.
- Ollama 선택 시 Gemini API key를 비활성화하고 Ollama URL을 활성화한다.
- Gemini 선택 시 Ollama URL을 비활성화하고 Gemini API key를 활성화한다.
- 필드뿐 아니라 연결된 라벨도 함께 흐리게 표시해 설정의 종속 관계를 명확히 했다.

## 주요 변경 파일

- `src/lecture_auto/gui/app.py`
- `tests/test_gui_smoke.py`

## 검증

- `pytest -q tests/test_gui_smoke.py`: 15 passed
- `pytest -q`: 268 passed, 기존 Ollama 통합 테스트 경고 2건
- 로컬 STT + Ollama 설정 화면 오프스크린 렌더링 및 시각 확인
- `scripts/build_macos_app.sh --install`: 성공
- 설치 앱 smoke 실행: 성공
- 설치 앱 `codesign --verify --deep --strict`: 성공
- `scripts/verify_lightweight_app.py`: 성공, FFmpeg/FFprobe 포함 확인

## 리스크/이슈

- 설정 스키마와 저장 규칙은 변경하지 않았다.
- 공용 LLM 모델, 언어, thinking level 입력은 provider와 무관하게 계속 편집 가능하다.

## 다음 작업

- 없음.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
- `redesign-existing-projects` 기준에 따라 관련 설정을 숨기지 않고 명확한 비활성 상태로 보여 provider 전환 결과를 예측할 수 있게 했다.
