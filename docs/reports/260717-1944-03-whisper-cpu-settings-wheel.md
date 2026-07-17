# 작업 기록 - Whisper CPU 고정 및 설정 휠 입력 차단

- 일시: 2026-07-17 19:44 (Asia/Seoul)
- 작업 유형: 버그 수정 / Windows 빌드

## 요약

- 로컬 Whisper가 자동으로 CUDA를 선택해 `cublas64_12.dll` 로딩에 실패하던 문제를 수정했다.
- 설정 화면에서 콤보박스와 숫자 입력값이 마우스 휠로 의도치 않게 변경되지 않도록 차단했다.
- Windows 독립 실행형 앱과 설치 프로그램을 다시 빌드했다.

## 변경 범위

- 로컬 Whisper worker가 `faster-whisper` 모델을 항상 CPU 장치로 생성하도록 명시했다.
- 설정 화면 전용 무휠 콤보박스, 정수 스핀박스, 실수 스핀박스를 추가했다.
- CPU 장치 전달과 휠 입력 무시 동작을 회귀 테스트로 추가했다.

## 주요 변경 파일

- `src/lecture_auto/local_ai_worker.py`
- `src/lecture_auto/gui/app.py`
- `tests/test_local_ai_worker.py`
- `tests/test_gui_smoke.py`

## 검증

- 대상 테스트: `19 passed`
- 전체 테스트: `287 passed`, 기존 `PytestReturnNotNoneWarning` 2건
- 실제 캐시된 `large-v3` 모델과 관리 런타임으로 CPU 전사 성공
- Windows 경량 패키징 검증 성공: x86_64, 금지 파일/모듈 없음, ffmpeg/ffprobe/템플릿 포함
- Windows GUI smoke test 성공
- 독립 실행형 크기: 474,888,772 bytes
- 설치 프로그램: `dist-installer/LectureAuto-Setup.exe`
- 설치 프로그램 크기: 131,028,070 bytes
- SHA-256: `D8DDCE3B9E12827A008ECA63093E39CDCB9C2AA86B5F214A15D82C35D46062D5`

## 리스크 및 이슈

- 로컬 Whisper는 GPU 가속 대신 CPU를 사용하므로 CUDA DLL 설치 상태와 무관하게 동작하지만 전사 속도는 GPU보다 느릴 수 있다.
- 설치 프로그램은 코드 서명되지 않았다.

## 다음 작업

- 필요하면 CUDA 라이브러리를 별도 관리하는 명시적 GPU 가속 옵션을 후속으로 설계한다.

## 참고

- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`
