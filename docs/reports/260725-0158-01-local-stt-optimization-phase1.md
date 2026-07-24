# 작업 기록 - 로컬 STT 최적화 1차

- 일시: 2026-07-25 01:58 (KST)
- 작성자: Hanbyul
- 에이전트: Codex
- 작업 유형: 기능 추가/성능 검증/문서화

## 요약

- faster-whisper의 device/compute/batch/VAD/beam/thread/hotword 설정을 전 UI와 worker 경계에 연결했다.
- confidence sidecar와 반복·저신뢰 구간 quality gate를 추가했다.
- 실제 오디오 refinement 이력과 checksum provenance를 기록한다.
- `recordings` corpus용 재현 가능한 benchmark harness를 만들고 graphics 강의를 비교했다.

## 변경 범위

- local worker 성능 profile, capability 기록, CUDA 오류 안내, batch OOM 축소 재시도
- raw transcript와 별도인 `*-raw.stt.json`
- STT quality 판정과 benchmark CER/WER/RTF/반복 지표
- config JSON, 환경변수, CLI, TUI, GUI 설정
- GUI/TUI 모델 선택과 한·영 README에 하드웨어별 권장 model/device/compute 안내
- audio refinement 실제 이력

## 주요 변경 파일

- `src/lecture_auto/stt_config.py`
- `src/lecture_auto/local_ai_worker.py`
- `src/lecture_auto/local_worker_adapter.py`
- `src/lecture_auto/stt_quality.py`
- `src/lecture_auto/stt_runtime.py`
- `src/lecture_auto/session_service.py`
- `scripts/benchmark_local_stt.py`

## 검증

- graphics 30:59, CPU/int8:
  - base 기존 sequential: 223.54초, RTF 0.1202, CER 1.2666
  - base batch4/beam1/VAD: 39.59초, RTF 0.0213, CER 1.3920
  - base batch4/beam5/VAD: 81.74초, RTF 0.0440, CER 1.3348
  - small batch4/beam1/VAD warm: 124.58초, RTF 0.0670, CER 1.1873
- deeplearning 118:08, small batch4/beam1/VAD warm:
  - 322.28초, RTF 0.0455, CER 0.8398
  - reference/hypothesis 길이비 0.936으로 graphics reference보다 정합성이 높음
  - 최대 동일 token run 112, high no-speech segment 98/170으로 fast-pass 단독 사용은 부적합
- 오디오 streaming preflight:
  - graphics: 평균 -32.14 dBFS, 무음 17.94%, 48 kHz mono
  - deeplearning: 평균 -33.93 dBFS, 무음 49.39%, 48 kHz mono
  - 두 파일 모두 드문 강한 peak가 있어 단순 positive gain보다 VAD와 limiter 포함 정규화 A/B가 필요
- base batch는 최대 동일 token run 103~105로 반복 루프가 심했다.
- small batch는 최대 run 4, 반복 초과 1로 반복 결함이 크게 줄고 base sequential보다 빠르고 정확했다.
- 전체 suite는 309개 통과. 기존 `tests/test_ollama_llm.py`의 3개 integration test는
  실행 중 Ollama server 부재로 실패했으며 이번 변경과 무관하다.

## 리스크/이슈

- 제공된 reference는 같은 강의 구간이지만 hypothesis의 약 53~57% 길이인 정제/축약본이다.
  CER/WER는 후보 간 상대 비교용이며 절대 ground truth 정확도로 해석하면 안 된다.
- RTX 4060 Ti는 감지되지만 `cublas64_12.dll`이 없어 CUDA profile 초기화가 실패한다.
- warm worker, 선택적 재전사/병합, 조건부 음질 preflight, refine audit는 후속 단계다.

## 다음 작업

- deeplearning 전체 corpus 결과 확정
- base sequential beam1+VAD와 small/large 후보 Pareto 추가 측정
- quality gate 기반 구간 재전사와 timestamp 병합
- warm worker와 조건부 오디오 전처리

## 참고

- 관련 문서: `docs/todo/260725-0127-01-local-stt-optimization.md`
