# 작업 기록 - PDF 자료 STT hotword 격리

- 일시: 2026-09-01 18:21 (KST)
- 작성자: OpenAI Codex
- 에이전트: Codex
- 작업 유형: 버그 수정

## 요약

- PDF/PPTX에서 자동 추출한 용어가 faster-whisper 디코딩을 오염시켜 자료 문구를 반복 생성하는 문제를 수정했다.
- 자료 용어는 STT hotword에서 제외하고 전사문 정제 문맥에서만 사용한다.

## 변경 범위

- local Whisper adapter 생성 시 사용자 설정 hotword와 세션 제목·과목 용어만 전달한다.
- PDF 자료를 가진 세션에서도 자료 본문이 hotword에 포함되지 않는 회귀 테스트를 추가했다.
- 기술 스펙, 제품 계획, 영문·한글 설정 문서와 README를 현재 동작에 맞췄다.

## 주요 변경 파일

- `src/lecture_auto/session_service.py`
- `tests/test_stt_gap_analysis.py`
- `docs/02-specs.md`
- `docs/03-product-plan.md`
- `docs/setup.md`, `docs/setup.ko.md`, `README.md`

## 검증

- `.venv/bin/pytest -q tests/test_stt_gap_analysis.py tests/test_local_stt_optimization_phase2.py tests/test_local_worker_adapter.py tests/test_local_ai_worker.py`: 27 passed
- `PYTHONPATH=. .venv/bin/pytest -q`: 340 passed, 1 skipped, 2 warnings
- `git diff --check`: 통과

## 리스크/이슈

- PDF/PPTX 전문용어는 raw STT 디코딩을 직접 편향하지 않지만 기존 LLM 정제 evidence에는 계속 포함된다.
- 이미 오염된 raw transcript는 자동으로 다시 생성하지 않는다.

## 다음 작업

- 없음

## 참고

- 재현 자료: `db-01.pdf`에서 추출된 hotword 문구와 `db-01-raw.md`의 반복 환각이 일치했다.
- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
