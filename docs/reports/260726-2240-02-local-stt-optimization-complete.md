# 작업 기록 - 로컬 STT 최적화 완료

- 일시: 2026-07-26 22:40 (KST)
- 작성자: Hanbyul
- 에이전트: Codex
- 작업 유형: 기능 추가/성능 검증/리팩터/문서화

## 요약

- 로컬 STT 최적화 TODO의 미완료 구현·평가 항목을 완료했다.
- 한국어 강의용 VAD/quality 기준, 제한된 선택적 재전사와 timestamp 병합,
  session/material glossary biasing, warm worker와 모델 LRU를 추가했다.
- 조건부 오디오 후보 정책, 안전한 LLM refine evidence/chunk/audit,
  확장 benchmark 지표와 optional 대형 모델/GPU 통합 테스트를 추가했다.
- 대안 backend/model은 모델 형식·cache·runtime·라이선스·패키징을 분리 평가하고
  검증 전 자동 채택하지 않는 정책으로 확정했다.

## 변경 범위

- benchmark:
  - CER/WER, 용어 recall, 숫자·수식 recall, 누락률, 무음 hallucination,
    반복, RTF, cold/warm wall time, peak RAM/VRAM, runtime/hardware/version
  - refine 전후 지표와 숫자·영문 named-term 변경 audit
  - profile/backend JSON 조회와 개인 corpus 없는 합성/mock 테스트
- faster-whisper:
  - 물리 core 기반 CPU thread, 보수적 worker 격리, warm model cache
  - 1차 fast pass와 앞뒤 문맥을 포함한 beam 5/강한 모델 선택적 재전사
  - 최대 8구간·120초 cap, 전체 저신뢰 시 model upgrade 제안
- 입력/용어/refine:
  - 64개·1,000자 glossary cap과 자료 기반 철자 bias
  - 반복 decode일 때만 16 kHz mono FLAC cache 후보
  - 저음량/high-pass/DeepFilterNet 조건과 raw 자동 보존
  - ASR evidence, `[불명확 mm:ss]`, 문장 경계 chunk, audit JSON

## 주요 변경 파일

- `scripts/benchmark_local_stt.py`
- `src/lecture_auto/local_runtime.py`
- `src/lecture_auto/local_ai_worker.py`
- `src/lecture_auto/local_worker_adapter.py`
- `src/lecture_auto/stt_quality.py`
- `src/lecture_auto/stt_profiles.py`
- `src/lecture_auto/stt_glossary.py`
- `src/lecture_auto/stt_audio_policy.py`
- `src/lecture_auto/stt_refinement.py`
- `src/lecture_auto/session_service.py`
- `src/lecture_auto/llm_adapter.py`
- `tests/test_local_stt_optimization_phase2.py`
- `tests/test_optional_local_stt_integration.py`

## 실측

환경: Windows x86_64, 6 physical/12 logical CPU, faster-whisper 1.2.1,
CTranslate2 4.8.1. `graphics` 1,859.45초 입력과 동일 reference를 사용했다.
reference가 실제 발화보다 짧은 정제/축약본이므로 CER/WER는 절대값이 아니라
같은 입력·reference의 상대 비교로만 해석한다.

| 후보 | wall/RTF | CER/WER | 누락률 | 반복 구간 | 결론 |
| --- | --- | --- | --- | ---: | --- |
| small/int8/batch4/beam1/VAD 2,000ms/condition off | warm 100.37초 / 0.0540 | 1.2959 / 1.6036 | 0.5561 | 272 | 긴 무음 경계에서 반복 악화 |
| 위와 동일/condition on | warm 98.47초 / 0.0530 | 1.2959 / 1.6036 | 0.5561 | 272 | transcript·정확도 동일 |
| small/int8/batch4/beam1/VAD 1,000ms/condition off | cold 97.88초 / 0.0526 | 1.1873 / 1.4670 | 0.5264 | 19 | fast/balanced profile 채택 |
| 위 1차 전사 + large-v3/beam5 선택 재전사 | cold 194.66초 / 0.1047 | 1.2203 / 1.5053 | 0.5172 | 18 | 3개 의심 구간만 재전사, 이 corpus에서는 CER 개선 없음 |

- warm worker 두 번째 실행은 `warm_start=true`, model load 약 0.00004초로
  동일 모델 인스턴스 재사용이 확인됐다.
- 1,000ms VAD는 2,000ms보다 hypothesis가 짧아졌지만 reference 누락률도 낮아져
  짧은 발화 손실 신호 없이 반복을 크게 줄였다.
- `condition_on_previous_text` A/B는 batched graphics corpus에서 결과가 완전히 같았다.
  1차 profile은 반복 격리를 위해 off, 품질 재전사는 문맥 보존을 위해 on을 쓴다.
- peak RAM은 small warm run에서 약 1.06 GB였다. CUDA device는 감지되지만
  이 환경에는 호환 cuBLAS/cuDNN이 없어 VRAM 실측은 optional integration으로 남긴다.
- 선택적 `large-v3` 재전사는 8구간·120초 상한 안에서 3개 구간만 처리했고 peak RAM은
  약 3.81 GB였다. 누락률과 반복 수는 소폭 낮아졌지만 CER/WER와 용어 recall은 개선되지
  않아, 재전사 기능은 유지하되 이 corpus만으로 자동 모델 승격을 정당화하지 않는다.
- 실제 한국어 Pareto 측정 범위에서는 `base`가 가장 빠르고 `small`이 정확도 우위,
  `large-v3` 선택 재전사는 약 2배 시간으로 품질 이득이 없었다. `turbo`는 NVIDIA
  중심 후보이나 이 머신의 CUDA runtime이 동작하지 않아 CPU 수치를 대표값처럼 기록하지
  않았다. GPU/Apple Silicon 후보는 optional integration으로 명시적으로 분리했다.

실측 산출물은 ignore 대상인 `build/stt-benchmarks/260726-local-stt-final-*.json`에 있다.

## Backend/model 평가

| 후보 | 판단 | 근거 |
| --- | --- | --- |
| faster-whisper | 채택 유지 | 현재 adapter/sidecar/VAD/batch/word timestamp와 호환 |
| whisper.cpp | optional benchmark | Metal/Core ML, OpenVINO, Vulkan, CUDA, ROCm을 지원하지만 native build/model format이 별도 |
| mlx-whisper | optional benchmark | Apple Silicon에 적합하지만 macOS 전용 add-on/model cache가 필요 |
| SenseVoiceSmall | optional benchmark | 한국어·CTC timestamp 후보, 약 944 MB; FunASR model license 고지 필요 |
| Qwen3-ASR-0.6B | optional benchmark | 한국어·forced aligner, Apache-2.0, 약 1.88 GB와 GPU 중심 runtime |
| Moonshine 한국어 | optional benchmark | 경량 latency 후보지만 Community License 표시 조건과 timestamp contract 추가 검토 필요 |
| Distil-Whisper | 한국어 기본 제외 | 공식 checkpoint가 영어 중심 |

평가 registry는 `python scripts/benchmark_local_stt.py --list-backends`로 확인한다.
채택하지 않은 backend는 현재 `STTRuntimeAdapter` 구현이나 기본 패키지 의존성에
추가하지 않아 lightweight import와 배포 크기를 보존한다.

## 검증

- 전체 회귀: 327 passed, 1 skipped
- 관련 unit/GUI/CLI 집중 회귀: 122 passed
- 새 phase 2 집중 테스트: 9 passed
- Windows 기존 standalone 경량 검증:
  `--app build/windows/LectureAuto.dist --report build/windows/nuitka-report.xml`
  성공, banned files/modules 없음
- `lecture-auto --help`, `lecture-auto config set --help`,
  benchmark `--help`, `--list-profiles`, `--list-backends` 성공
- 실제 대형 모델/GPU 테스트는
  `LECTURE_AUTO_RUN_LARGE_STT_INTEGRATION=1`일 때만 실행한다.

## 리스크/이슈

- 현재 제공 reference는 발화 전체의 verbatim ground truth가 아니므로 자동 threshold는
  `ko-lecture-v1` 초기 corpus 보정값이다. 새로운 정렬 corpus가 생기면 같은 harness로
  재보정해야 한다.
- DeepFilterNet은 현재 managed runtime에 설치되지 않아 이번 머신에서는 실제 denoise
  RTF를 만들지 않았다. 코드 정책은 raw/processed의 CER·term recall과 추가 RTF를 함께
  요구하고, 개선이 없으면 raw를 선택한다.
- optional backend는 현재 머신에 해당 가속기/runtime이 없어 공식 기능·라이선스·
  패키징 평가로 종료했다. 검증되지 않은 성능 수치를 기록하지 않았다.

## 다음 작업

- 없음. 새 정렬 corpus나 새 대상 하드웨어가 제공되면 동일 benchmark를 다시 실행한다.

## 참고

- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`,
  `docs/03-product-plan.md`, `docs/setup.ko.md`
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [OpenAI Whisper model card](https://github.com/openai/whisper/blob/main/model-card.md)
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp)
- [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice)
- [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)
- [Moonshine Korean model license](https://huggingface.co/UsefulSensors/moonshine-tiny-ko/blob/main/LICENSE.txt)
