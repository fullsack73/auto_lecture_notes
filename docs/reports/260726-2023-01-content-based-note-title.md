# 작업 기록 - 내용 기반 노트 제목

- 일시: 2026-07-26 20:23 (Asia/Seoul)
- 작업 유형: 기능 개선

## 요약

- 구조화 노트의 최상위 제목을 `Structured Lecture Notes` 고정 문구에서 강의 내용 기반 제목으로 변경했다.
- Gemini와 Ollama가 공통 JSON schema의 `note_title`을 생성하고 앱이 이를 Markdown H1으로 렌더링한다.

## 변경 범위

- 구조화 노트 JSON schema에 문자열 `note_title` 추가
- Ollama의 `topic_overview` 요청에서 제목을 함께 생성해 provider 호출 수 유지
- 누락되거나 일반적인 제목은 첫 번째 topic overview 항목으로 fallback
- 상세 설명 제목이 최상위 제목을 덮어쓰지 않도록 renderer 변수 분리
- 템플릿과 사용자·제품·기술 문서 갱신

## 검증

- 관련 노트 생성 테스트: `40 passed`
- 전체 테스트: `316 passed`, 기존 `PytestReturnNotNoneWarning` 2건
- 모델 생성 제목 렌더링과 기존 고정 제목 fallback 회귀 테스트 추가
- `git diff --check` 통과

## 리스크 및 대응

- 기존 provider 응답에 `note_title`이 없어도 topic overview 기반 제목을 사용해 호환성을 유지한다.
- 제목이 100자를 넘으면 Markdown 가독성을 위해 단어 경계에서 줄인다.

## 참고

- 관련 코드: `src/lecture_auto/llm_adapter.py`
- 관련 템플릿: `src/lecture_auto/templates/structured-notes.md`
- 관련 테스트: `tests/test_ollama_note_harness.py`, `tests/test_llm_adapters_and_config.py`
