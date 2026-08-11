# 작업 기록 - 전사문 문맥 보정 복원

- 일시: 2026-08-11 20:19 (KST)
- 작성자: OpenAI Codex
- 에이전트: Codex
- 작업 유형: 버그 수정

## 요약

- 저신뢰 ASR 구간을 지나치게 보존하던 refine 지시를 수정해 문맥상 분명한 발음 유사 오인식과 깨진 표현을 다시 교정하도록 복원했다.

## 변경 범위

- 기존 LLM provider 공용 refine prompt와 ASR evidence 규칙만 변경했다.
- sidecar evidence, 숫자·고유명사 audit, provider adapter 경계와 출력 형식은 유지했다.

## 주요 변경 파일

- `src/lecture_auto/llm_adapter.py`
- `src/lecture_auto/stt_refinement.py`
- `tests/test_llm_adapters_and_config.py`
- `tests/test_local_stt_optimization_phase2.py`
- `docs/02-specs.md`

## 검증

- `.venv/bin/pytest -q tests/test_llm_adapters_and_config.py tests/test_local_stt_optimization_phase2.py tests/test_transcript_refine_command.py tests/test_llm_refinement_gaps.py`: 37 passed
- `PYTHONPATH=.:src .venv/bin/pytest -q`: 336 passed, 1 skipped, 2 existing warnings

## 리스크/이슈

- 실제 교정 결과는 선택한 LLM 모델 성능에 영향을 받는다.
- 숫자·수식·고유명사는 문맥 근거가 강한 경우에만 교정하도록 제한하고 변경 내역을 audit JSON에 남긴다.

## 다음 작업

- 없음.

## 참고

- 관련 문서: `docs/02-specs.md`
- 회귀 원인: `336d2e9`에서 추가된 저신뢰 구간 보존 지시
