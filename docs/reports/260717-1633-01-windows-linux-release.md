# 작업 기록 - Windows/Linux 설치 파일 Release 배포

- 일시: 2026-07-17 16:33 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 기능 추가/배포/문서화

## 요약

- `dev`의 Windows/Linux 네이티브 빌드를 최신 `master`와 정렬하고, Windows x86_64 설치 파일과 Linux x86_64 AppImage/portable archive를 버전 Release에 게시하는 흐름을 추가했다.

## 변경 범위

- 기존 Nuitka standalone 및 Inno Setup/linuxdeploy 패키징을 GitHub Release 흐름에 연결
- 고정 FFmpeg LGPL 바이너리 checksum 검증, 번들 및 라이선스 고지 유지
- 태그 기반 GitHub Release 생성과 SHA-256 목록 게시
- README와 설치/기술/제품 문서의 다운로드 안내

## 주요 변경 파일

- `.github/workflows/desktop-build.yml`
- `deployment/README.md`
- `README.md`, `docs/README.ko.md`, `docs/setup*.md`

## 검증

- `pytest -q`
- `python scripts/verify_lightweight_app.py`
- GitHub Actions `workflow_dispatch` Windows/Linux 네이티브 패키지 빌드
- 태그 빌드 후 GitHub Release asset 확인

## 리스크/이슈

- 설치 파일에 공개 코드 서명이 없어 운영체제가 확인 경고를 표시할 수 있다.
- macOS 공개 배포본은 없으며 Apple Silicon 로컬 빌드 경로를 유지한다.

## 다음 작업

- 코드 서명 인증서가 준비되면 Windows Authenticode와 macOS Developer ID/공증을 추가한다.

## 참고

- 관련 문서: `deployment/README.md`, `docs/02-specs.md`, `docs/03-product-plan.md`
