# 작업 기록 - Windows/Linux GUI 빌드

- 일시: 2026-07-17 03:25 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 기능 추가/리팩터/문서화

## 요약

- macOS 앱과 같은 Nuitka 기반 네이티브 GUI 빌드 경로를 Windows와 Linux에 추가했다.
- Windows x86_64 standalone 및 Inno Setup installer, Linux x86_64/ARM64 standalone·tar.gz·AppImage를 지원한다.
- Windows와 WSL2 Linux x86_64에서 실제 빌드와 패키지 실행을 검증했다.

## 변경 범위

- 공통 Windows/Linux Nuitka 빌더와 플랫폼 wrapper 추가
- 고정 BtbN LGPL FFmpeg/FFprobe 다운로드, SHA-256, MP3, 녹음 backend, 라이선스 검증
- Windows installer와 Linux desktop/AppRun/AppImage 구성
- 플랫폼 공통 패키징 verifier와 GUI smoke launch
- compiled standalone에서 worker와 `uv`를 찾도록 local runtime 경로 일반화
- GitHub Actions desktop matrix가 로컬과 동일한 빌드 스크립트를 사용하도록 변경
- 영문/한글 README, setup, 구조/스펙/제품 문서 갱신

## 주요 변경 파일

- `scripts/build_desktop_app.py`
- `scripts/build_windows_app.ps1`
- `scripts/build_linux_app.sh`
- `scripts/prepare_ffmpeg_desktop.py`
- `scripts/prepare_desktop_icon.py`
- `scripts/verify_lightweight_app.py`
- `deployment/windows.iss`
- `deployment/linux/`
- `.github/workflows/desktop-build.yml`
- `src/lecture_auto/local_runtime.py`

## 검증

- `pytest -q`: 276 passed, 기존 Ollama test return warning 2건
- Windows build: `scripts/build_windows_app.ps1` 성공
- Windows verifier: x86_64, 474,859,108 bytes, FFmpeg/FFprobe·template·worker·uv·license 포함, banned AI dependency 0, GUI smoke 성공
- Windows installer: `scripts/build_windows_app.ps1 -InstallerOnly` 성공, `dist-installer/LectureAuto-Setup.exe` 131,017,478 bytes
- Linux build(WSL2 Ubuntu x86_64): standalone verifier 및 headless GUI smoke 성공, 557,174,690 bytes
- Linux AppImage: `bash scripts/build_linux_app.sh --appimage-only` 성공, 232,204,792 bytes
- Linux AppImage 자체 `APPIMAGE_EXTRACT_AND_RUN=1` headless smoke 성공
- PowerShell parser, `bash -n`, `py_compile`, `git diff --check`, `lecture-auto --help` 성공

## 리스크/이슈

- Windows installer와 Linux AppImage는 코드 서명되지 않았다.
- AppImage/standalone은 빌드 배포판의 glibc 호환성 영향을 받으므로 공개 artifact는 CI의 Ubuntu 22.04 빌드를 기준으로 한다.
- Linux AppImage 패키징에는 Qt XCB/XKB 개발 머신 패키지가 필요하며 setup 문서와 CI에 명시했다.

## 다음 작업

- 공개 배포가 필요해지면 Windows code signing, macOS Developer ID/notarization, Linux release signing 정책을 별도 수립한다.

## 참고

- 관련 문서: `README.md`, `docs/README.ko.md`, `docs/setup.md`, `docs/setup.ko.md`, `deployment/README.md`
