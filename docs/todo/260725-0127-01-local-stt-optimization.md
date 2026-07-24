# TODO - 로컬 STT 정확도·처리시간 최적화

- 등록 일시: 2026-07-25 01:27 (KST)
- 작성자: Hanbyul / Codex
- 에이전트: Codex
- 진행 시점: 즉시 시작. 단계별 벤치마크 결과에 따라 후속 구현.

## 목표

- 로컬 STT를 강의 길이보다 충분히 빠르게 처리하면서 한국어 강의의 내용, 전문용어, 숫자, 수식 보존율을 높인다.
- 작은 모델의 전체 1차 전사와 낮은 신뢰도 구간의 선택적 고품질 재전사를 결합한다.
- LLM 정제는 ASR가 잃은 사실을 추측하지 않고, 증거가 있는 오류만 보수적으로 수정한다.
- CPU, NVIDIA GPU, Apple Silicon, 기타 GPU에서 합리적인 실행 backend/profile을 자동 또는 명시적으로 선택할 수 있게 한다.

## 요구사항

### 1. 재현 가능한 벤치마크

- [x] `D:\lecture_auto\recordings`의 아래 로컬 사용자 데이터를 기본 벤치마크 corpus로 사용한다. 저장소에는 추가/커밋하지 않는다.
  - `test-deeplearning.mp3` + `transcript-deeplearning.md`
  - `test-graphics.mp3` + `transcript-graphics.md`
- [x] 파일명 규칙 또는 manifest로 오디오와 정답 전사문을 연결한다.
- [x] corpus 전체 실행과 파일 선택 실행을 지원한다.
- [x] baseline과 후보 설정을 동일 입력에서 반복 실행하고 JSON/Markdown 결과를 남긴다.
- [ ] 최소 측정값:
  - 한국어 CER
  - 가능하면 어절 WER
  - 전문용어/고유명사 recall
  - 숫자·수식 recall
  - 누락률
  - 무음/음악 hallucination 수와 반복 구간 수
  - RTF(real-time factor), 총 처리시간
  - cold start와 warm start 시간
  - peak RAM/VRAM
- [ ] LLM refine 전후를 별도 평가하고 새 사실 추가, 숫자 변경, 고유명사 임의 변경을 검출한다.
- [ ] 개인 녹음/정답이 없는 CI에서는 합성·mock fixture로 harness 동작만 검증한다.
- [ ] 모델/런타임/하드웨어/옵션/version을 결과에 기록한다.

### 2. faster-whisper 설정과 빠른 1차 전사

- [x] `STTConfig`에 하위 호환 기본값을 가진 로컬 성능 설정을 추가한다.
  - `device`: `auto|cpu|cuda`
  - `compute_type`: `auto|int8|int8_float16|float16|float32`
  - `batch_size`
  - `beam_size`
  - `temperature`
  - `vad_filter`
  - `vad_min_silence_duration_ms`
  - `condition_on_previous_text`
  - `word_timestamps`
  - `hotwords` 또는 glossary 경로
  - `cpu_threads`
  - 선택적 `num_workers`
- [x] worker adapter가 모든 설정을 provider 경계 뒤에서 전달하게 한다.
- [x] 알려진 강의 언어는 `ko`처럼 고정하여 언어 감지 비용/오류를 줄인다.
- [x] `BatchedInferencePipeline`을 선택적으로 사용한다.
- [x] 메모리/VRAM 부족 시 batch size를 절반씩 줄여 재시도하고 실제 batch를 기록한다.
- [x] fast profile은 `beam_size=1`, `temperature=0`을 후보로 검증한다.
- [x] quality 후보로 `beam_size=5`와 기존 fallback 동작을 비교한다.
- [ ] VAD는 기본적으로 보수적 설정부터 검증하고 짧은 발화를 잘라내지 않게 한다.
- [ ] `condition_on_previous_text=False`의 반복/hallucination 감소와 문맥 일관성 손실을 A/B 평가한다.
- [ ] segment 생성기 iteration이 실제 추론 단계임을 유지하고 progress/cancel 동작을 깨지 않는다.

### 3. 하드웨어별 실행 profile/backend

- [x] CTranslate2가 지원하는 compute type을 runtime에서 질의한다.
- [x] NVIDIA CUDA 사용 가능 시 `float16` 또는 `int8_float16`을 자동 후보로 선택한다.
- [ ] CPU에서는 `int8`과 물리 core 기반 thread 수를 기본 후보로 삼고 oversubscription을 막는다.
- [x] GPU 초기화/라이브러리 오류 시 조용한 CPU fallback 대신 사용자에게 실제 선택과 실패 이유를 표시한다.
- [ ] profile 예시를 제공한다.
  - CPU fast: `base/int8/VAD/batch/beam1`
  - CPU balanced: `small/int8/VAD/batch`
  - NVIDIA balanced: `turbo/float16` 또는 `int8_float16`
  - quality retry: `small|turbo|large-v3/beam5`
- [ ] Apple Silicon에서 `whisper.cpp` Metal/Core ML 또는 MLX backend를 provider adapter 후보로 벤치마크한다.
- [ ] Intel GPU/CPU OpenVINO, AMD/NVIDIA Vulkan/ROCm을 지원하는 `whisper.cpp` backend의 배포 복잡도와 성능을 평가한다.
- [ ] backend별 모델 형식, 다운로드, 캐시, 라이선스, 패키징을 분리 관리한다.

### 4. warm worker와 모델 수명주기

- [ ] 전사마다 Python worker와 Whisper 모델을 다시 생성하는 현재 cold-start 경로를 측정한다.
- [ ] 장수 worker/로컬 서버 또는 안전한 worker pool을 설계한다.
- [ ] 모델명·device·compute type별 인스턴스를 재사용한다.
- [ ] idle timeout, 명시적 unload, VRAM/RAM 부족 시 LRU 제거를 지원한다.
- [ ] 앱 종료, 취소, worker crash 시 자식 프로세스와 메모리를 정리한다.
- [ ] add-on 격리와 앱 lightweight import 원칙을 유지한다.

### 5. 신뢰도 보존과 선택적 재전사

- [x] segment별 아래 정보를 공용 결과/내부 artifact에 보존한다.
  - 시작/종료 시각
  - `avg_logprob`
  - `compression_ratio`
  - `no_speech_prob`
  - temperature
  - 선택적 word probability/timestamp
- [x] 기존 raw Markdown과 공개 JSON 호환성을 깨지 않는 `*-raw.stt.json` sidecar를 사용한다.
- [x] 낮은 신뢰도/hallucination/반복 후보를 판정하는 1차 quality gate를 구현한다.
  - 낮은 평균 log probability
  - 높은 compression ratio
  - VAD상 음성인데 빈 결과
  - 동일 n-gram 비정상 반복
  - 비정상적인 token/초
  - 의심스러운 숫자·수식·전문용어
- [ ] faster-whisper 기본 fallback 값(`-1.0`, `2.4`, `0.6`)을 초기 후보로만 사용하고 한국어 corpus로 보정한다.
- [ ] 의심 구간에 앞뒤 1~2초 문맥을 붙여 더 강한 모델/beam으로 재전사한다.
- [ ] 1차/2차 결과를 timestamp 기준으로 안정적으로 병합한다.
- [ ] 전체 구간이 낮은 신뢰도면 전체 모델 승격을 제안하거나 자동 실행하는 정책을 정의한다.
- [ ] 재전사 횟수와 시간 상한을 두어 무한 retry를 막는다.

### 6. 강의 자료와 용어 biasing

- [ ] 제목, 과목, PDF/PPT/PPTX에서 고유명사·전문용어·영문 약어 glossary를 추출한다.
- [ ] glossary를 `hotwords`/`initial_prompt`로 STT에 전달한다.
- [ ] 지나치게 긴 prompt와 잘못된 bias가 일반 문장 인식을 해치지 않도록 길이/개수 제한과 A/B 검증을 둔다.
- [ ] 자료에만 있고 실제 발화되지 않은 내용이 transcript에 삽입되지 않게 한다.

### 7. 오디오 입력과 조건부 전처리

- [ ] 가능하면 마이크보다 system loopback 원음을 우선하도록 안내/진단한다.
- [x] clipping, 평균/peak loudness, silence 비율, 채널, sample rate를 streaming preflight에서 측정한다.
- [ ] faster-whisper가 내부적으로 16 kHz mono 변환하므로 사전 변환의 이득을 decode/storage와 model inference로 분리 측정한다.
- [ ] 캐시가 유리한 경우에만 16 kHz mono PCM/FLAC canonical audio를 만든다.
- [ ] raw, volume-normalized, denoised 입력을 별도 후보로 유지해 원본을 덮어쓰지 않는다.
- [ ] `dynaudnorm`은 조용한 잡음까지 증폭할 수 있으므로 전 구간 기본 적용하지 않는다.
- [ ] loudness가 실제로 낮을 때만 `loudnorm`/가벼운 speech normalization을 검증한다.
- [ ] 저주파 진동이 심한 입력에서만 가벼운 high-pass를 검증한다.
- [ ] 지속 잡음이 음성을 가리는 저 SNR 입력에서만 DeepFilterNet을 검증한다.
- [ ] DeepFilterNet의 추가 RTF와 CER 개선을 함께 측정한다.
- [ ] raw보다 CER/핵심어 recall이 나빠지면 자동으로 원본 경로를 선택한다.
- [x] VAD를 음질 필터보다 우선 적용한 benchmark profile을 구현하고 corpus에서 검증한다.
- [x] `audio_amplification_applied`가 설정값이 아니라 실제 사용한 artifact/filter를 반영하도록 수정한다.
- [x] refinement 순서, 파라미터, source/output checksum을 provenance로 기록한다.

### 8. LLM transcript refine 안전성

- [ ] refine 입력에 segment timestamp, confidence, 1차/2차 ASR 후보, 앞뒤 문맥을 선택적으로 제공한다.
- [ ] 강의 자료는 glossary/검증 근거로만 사용하고 발화 사실의 대체 근거로 사용하지 않는다.
- [ ] LLM이 수행할 범위를 문장부호, 띄어쓰기, 문장 경계, 명백한 용어 오타, 무의미 반복 정리로 제한한다.
- [ ] 누락 문장, 숫자, 수식, 고유명사를 근거 없이 생성하지 못하게 한다.
- [ ] 후보가 충돌하거나 신뢰도가 낮으면 `[불명확 mm:ss]` 형태로 보존한다.
- [ ] 독립 chunk 경계에서 문장이 끊기거나 중복/누락되지 않도록 overlap 또는 segment 기반 chunking을 도입한다.
- [ ] 원문→수정문 diff/audit artifact를 선택적으로 남긴다.
- [ ] refine 전후 CER, 핵심어 recall, 숫자 보존, 새 사실 추가를 benchmark한다.

### 9. 대안 로컬 STT provider 평가

- [ ] SenseVoiceSmall을 한국어 CPU/저사양 후보로 평가한다.
- [ ] Qwen3-ASR-0.6B를 한국어 GPU 정확도 후보로 평가한다.
- [ ] 필요 시 한국어 Moonshine 경량 모델을 latency 후보로 평가한다.
- [ ] Whisper `turbo`, `small`, `base`, `large-v3`의 실제 한국어 강의 Pareto frontier를 측정한다.
- [ ] 영어 전용 Distil-Whisper는 한국어 기본 후보에서 제외한다.
- [ ] 각 모델의 weight/license, 상업 배포 조건, runtime 의존성, 다운로드 크기, RAM/VRAM, timestamp 지원을 검토한다.
- [ ] 채택 모델은 기존 `STTRuntimeAdapter` 경계 뒤에 구현한다.

### 10. 사용자 설정·호환성·검증

- [x] 새 설정을 config JSON, 환경변수, CLI, TUI, GUI에서 일관되게 제공한다.
- [x] 기존 config에 필드가 없어도 현재 workflow가 동작한다.
- [ ] 사람이 읽는 CLI 출력과 `--json` contract를 불필요하게 깨지 않는다.
- [x] 실제 device/compute/모델/배치/VAD와 batch 재시도 횟수를 progress 결과/sidecar에 표시한다.
- [ ] 설정 validation, worker request, batch fallback, VAD, confidence gate, merge, benchmark 계산 테스트를 추가한다.
- [ ] `pytest -q`, `python scripts/verify_lightweight_app.py`, CLI help, GUI smoke를 실행한다.
- [ ] GPU/대형 모델 통합 테스트는 자격 증명 없는 선택적 테스트로 분리한다.
- [x] 1차 구조/설정/사용자 흐름 변경을 `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`, 사용자 설정 문서에 반영한다.
- [ ] 완료 시 작업 보고서를 작성하고 이 TODO 및 목록 항목을 제거한다.

## 작업 요약

- 1차 구현: benchmark harness, faster-whisper perf config 전달, VAD/batch/device 선택, confidence 수집.
- 2차 구현: 선택적 재전사와 glossary biasing.
- 3차 구현: warm worker, 조건부 오디오 전처리, LLM refine audit.
- 4차 평가: 플랫폼 backend와 대안 한국어 모델.

## 선행조건

- 로컬 benchmark runtime에 `faster-whisper`와 대상 모델이 설치되어 있어야 한다.
- GPU profile은 호환 CUDA/cuDNN 또는 각 backend runtime이 필요하다.
- 정확도 비교를 위해 recordings의 transcript가 실제 오디오와 충분히 정렬된 정답이어야 한다.
- 사용자 녹음과 전사문은 계속 `.gitignore` 대상이어야 한다.

## 참고

- 관련 코드:
  - `src/lecture_auto/stt_config.py`
  - `src/lecture_auto/local_worker_adapter.py`
  - `src/lecture_auto/local_ai_worker.py`
  - `src/lecture_auto/local_runtime.py`
  - `src/lecture_auto/session_service.py`
  - `src/lecture_auto/llm_adapter.py`
- 관련 외부 자료:
  - https://github.com/SYSTRAN/faster-whisper
  - https://opennmt.net/CTranslate2/performance.html
  - https://github.com/openai/whisper
  - https://github.com/ggml-org/whisper.cpp
  - https://github.com/QwenAudio/SenseVoice
  - https://github.com/QwenLM/Qwen3-ASR
  - https://arxiv.org/abs/2305.08227
- `docs/todo/00-todo-list.md` 요약: 로컬 STT benchmark, VAD/배치/가속, 신뢰도 기반 재전사, 조건부 오디오 보정, 안전한 refine, 대안 provider를 구현·검증한다.
