# 작업 기록 - Windows 마이크 장치 탐지 수정

- 일시: 2026-07-17 20:11 (Asia/Seoul)
- 작업 유형: 버그 수정 / Windows 빌드

## 요약

- 최신 번들 FFmpeg의 DirectShow 장치 출력 형식을 인식하지 못해 Windows 마이크 목록이 비던 문제를 수정했다.
- 신형 typed 출력과 기존 section 기반 출력을 모두 지원한다.
- Windows standalone 앱과 설치 프로그램을 다시 빌드했다.

## 변경 범위

- `"장치명" (audio)` 형식의 DirectShow 장치를 오디오 입력으로 파싱한다.
- 기존 `DirectShow audio devices` section 형식과의 호환성을 유지한다.
- FFmpeg 장치 출력은 UTF-8로 읽고 잘못된 바이트는 대체해 비영문 장치명에서 전체 탐지가 실패하지 않게 한다.

## 주요 변경 파일

- `src/lecture_auto/capture_runtime.py`
- `tests/test_capture_runtime_device_resolution.py`

## 검증

- 관련 테스트: `27 passed`
- 전체 테스트: `289 passed`, 기존 `PytestReturnNotNoneWarning` 2건
- 실제 새 번들 FFmpeg로 `Microphone(USB Audio Device)` 탐지 성공
- Windows standalone 패키징 검증 성공: x86_64, 금지 파일/모듈 없음, FFmpeg/FFprobe/템플릿 포함, GUI smoke test 성공
- standalone 크기: 474,890,820 bytes
- 설치 프로그램: `dist-installer/LectureAuto-Setup.exe`
- 설치 프로그램 크기: 131,024,041 bytes
- SHA-256: `5A2CB79259F89D89A49DC5EBA20427E62B1B0E7A7AB941D66D6F2F9002053AC5`

## 리스크 및 이슈

- 설치 프로그램은 코드 서명되지 않았다.
- Windows에서 비활성화되었거나 OS 개인정보 설정으로 차단된 장치는 FFmpeg가 열거하지 못할 수 있다.

## 다음 작업

- 없음.

## 참고

- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`
