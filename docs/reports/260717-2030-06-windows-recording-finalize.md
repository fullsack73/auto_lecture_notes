# 작업 기록 - Windows 녹음 파일 정상 종료 수정

- 일시: 2026-07-17 20:30 (Asia/Seoul)
- 작업 유형: 버그 수정 / Windows 빌드

## 요약

- Windows에서 녹음 중지 후 0-byte WAV가 남아 재생·전사가 불가능하던 문제를 수정했다.
- 마이크 탐지와 폴더 열기 수정까지 포함한 Windows standalone 앱과 설치 프로그램을 다시 빌드했다.

## 변경 범위

- FFmpeg 프로세스의 표준 입력을 제어 파이프로 유지한다.
- 정상 녹음 중지는 Windows 강제 종료 대신 FFmpeg `q` 명령을 보내 컨테이너 헤더와 오디오 데이터를 flush한다.
- 제한 시간 내 종료하지 않거나 조기 종료된 FFmpeg를 명확한 runtime/device 오류로 변환한다.
- 사용자 취소/실패 경로는 기존 강제 종료 동작을 유지하고 프로세스를 회수한다.

## 주요 변경 파일

- `src/lecture_auto/capture_runtime.py`
- `tests/test_capture_cross_platform.py`

## 검증

- 수정 전 실제 앱 runtime 경로: 1.5초 녹음 후 0 bytes, ffprobe 실패 재현
- 수정 후 실제 앱 runtime 경로: 264,678 bytes, PCM s16le, 44.1 kHz, stereo, 1.500초, ffprobe 성공
- 실제 검증용 임시 녹음 파일 삭제 완료
- 관련 테스트: `22 passed`
- 전체 테스트: `294 passed`, 기존 `PytestReturnNotNoneWarning` 2건
- Windows standalone 패키징 검증 성공: x86_64, 금지 파일/모듈 없음, FFmpeg/FFprobe/템플릿 포함, GUI smoke test 성공
- standalone 디렉터리 크기: 474,893,892 bytes
- 실행 파일 크기: 74,336,256 bytes
- 설치 프로그램: `dist-installer/LectureAuto-Setup.exe`
- 설치 프로그램 크기: 131,044,062 bytes
- SHA-256: `7F503773E2F2DF0AD8668D1F4B376FBA5D0C41F5D1BB63AF70D704130FADCF72`

## 리스크 및 이슈

- 설치 프로그램은 코드 서명되지 않았다.
- 사용자가 실패/취소로 녹음을 중단한 경우 부분 파일은 완성본으로 보장하지 않는다.

## 다음 작업

- 없음.

## 참고

- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`
