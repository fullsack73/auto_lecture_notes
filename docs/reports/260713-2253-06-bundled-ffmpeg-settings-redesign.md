# 작업 기록 - FFmpeg 번들과 설정 관리 UI 리팩터

- 일시: 2026-07-13 22:53 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 버그 수정/패키징/GUI 리팩터/문서화

## 요약

- macOS 앱에 ARM64 FFmpeg와 FFprobe가 빠져 녹음 장치 확인이 실패하던 문제를 수정했다.
- 앱 번들 미디어 도구를 시스템 PATH보다 우선하도록 녹음, 오디오 정제, STT 분할, 녹음 병합 경로를 통일했다.
- 설정 화면의 동일한 버튼 12개를 상태·설치·유지보수·모델 작업으로 재구성했다.

## 변경 범위

- 고정 버전과 SHA-256으로 FFmpeg 7.1.5 및 LAME 3.100 소스를 준비하는 macOS 스크립트 추가
- GPL/nonfree 기능 비활성화, AVFoundation·MP3·dynaudnorm을 포함한 정적 ARM64 빌드
- FFmpeg/FFprobe, LGPL/LAME 라이선스, 소스 URL/checksum을 앱에 포함
- 앱 빌드 검증에 미디어 도구 존재·아키텍처·라이선스 설정·AVFoundation·MP3 지원 확인 추가
- Runtime 설치 대상을 드롭다운 하나로 통합하고 상태 확인과 유지보수 작업의 시각적 위계 분리
- Whisper와 Ollama 모델 작업을 목적별 2열 패널로 재배치
- `redesign-existing-projects` 지침에 따라 기존 PySide6와 색상 체계를 유지하며 버튼 도배와 동일 우선순위를 제거

## 주요 변경 파일

- `scripts/prepare_ffmpeg_macos.sh`
- `scripts/build_macos_app.sh`
- `scripts/verify_lightweight_app.py`
- `src/lecture_auto/capture_runtime.py`
- `src/lecture_auto/audio_amplifier.py`
- `src/lecture_auto/stt_runtime.py`
- `src/lecture_auto/session_service.py`
- `src/lecture_auto/gui/app.py`
- `tests/test_capture_cross_platform.py`
- `tests/test_gui_smoke.py`
- `docs/02-specs.md`
- `docs/03-product-plan.md`
- `deployment/README.md`

## 검증

- 관련 GUI/녹음/STT 테스트: 43 passed
- `pytest -q`: 267 passed, 기존 Ollama 통합 테스트 경고 2건
- 설정 Runtime/모델 패널 1280×820 시각 검수
- 준비 FFmpeg로 MP3 생성 → dynaudnorm → WAV 변환 → FFprobe 확인 성공
- FFmpeg/FFprobe ARM64 확인 및 `/opt/homebrew`, `/usr/local` dylib 비의존성 확인
- `scripts/build_macos_app.sh --install`: 성공
- Homebrew 경로가 없는 PATH에서 설치 앱 smoke 실행: 성공
- 설치 앱 내부 FFmpeg로 MP3/WAV 처리: 성공
- `codesign --verify --deep --strict`: 성공
- `scripts/verify_lightweight_app.py`: 번들 미디어 도구 확인, 금지 파일 및 모듈 없음

## 리스크/이슈

- FFmpeg 의존성을 포함해 앱 크기가 약 266MB로 증가했다.
- 최초 FFmpeg 준비에는 네트워크와 Xcode Command Line Tools가 필요하며 이후 빌드는 검증된 cache를 재사용한다.
- macOS 앱은 ad-hoc 서명이며 배포용 Developer ID 서명은 아니다.

## 다음 작업

- 배포 시 현재 소스 URL/checksum과 라이선스 고지가 유지되는지 확인한다.

## 참고

- FFmpeg source: `https://ffmpeg.org/releases/ffmpeg-7.1.5.tar.xz`
- LAME source: `https://download.videolan.org/pub/contrib/lame/lame-3.100.tar.gz`
- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`
