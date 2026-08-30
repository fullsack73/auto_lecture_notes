# 작업 기록 - macOS Python 3.13 실행 회귀 방지

- 일시: 2026-08-30 17:14 (Asia/Seoul)
- 작성자: fullsack73
- 에이전트: Codex
- 작업 유형: 버그 수정/패키징

## 요약

- v0.1.6 macOS 설치본이 실행 직후 종료되는 현상을 재현했다.
- Nuitka 앱이 로컬 `.venv`의 Python 3.13.3으로 빌드되어 Ollama가
  `pydantic_core`를 불러올 때 `datetime_CAPI` panic이 발생한 것이 원인이었다.
- macOS 앱 빌드를 ARM64 Python 3.11로 제한하고 잘못된 후보 앱이 기존 설치본을
  교체하지 못하도록 설치 전 smoke test를 강화했다.

## 변경 범위

- macOS 빌드 시작 전 Python 3.11 exact preflight
- Nuitka report의 실제 Python 버전 사후 검증
- smoke test에서 Ollama/pydantic import 경로 강제
- 설치 staging 후보를 실제 실행한 뒤에만 기존 앱과 교체
- macOS 빌드 문서를 `python3.11` 기준으로 수정

## 주요 변경 파일

- `scripts/build_macos_app.sh`
- `scripts/verify_lightweight_app.py`
- `scripts/install_macos_app.py`
- `tests/test_release_version.py`
- `tests/test_verify_lightweight_app.py`
- `tests/test_install_macos_app.py`
- `docs/setup.ko.md`
- `docs/setup.md`

## 검증

- Python 3.13.3 설치본 직접 실행 시 동일 panic 및 exit code 1 재현
- 기존 v0.1.6 Nuitka report에서 Python 3.13.3 사용 확인
- Python 3.13 preflight가 exit code 2로 종료하고 기존 빌드 산출물을 보존하는지 확인
- Python 3.13 Nuitka report의 사후 검증 실패 확인
- 관련 GUI·설정·패키징 테스트: 40 passed
- 외부 Ollama 실서비스 테스트를 제외한 전체 테스트: 336 passed, 1 skipped
- Python 3.11.15 ARM64 v0.1.6 빌드 및 Ollama 경로 GUI smoke test 통과
- staging 후보 실행과 deep code-sign 검증 후 안전 교체 설치 성공
- 빌드본과 설치본 실행 파일 SHA-256 일치:
  `572a281f042e82fd02a373b6f580bcbe908845bf4f30b5e64b4035c676b97cde`
- 실제 사용자 설정으로 설치본 실행 후 프로세스 유지 확인

## 리스크/이슈

- 일반 CLI/TUI의 Python 3.11+ 지원 범위는 바꾸지 않는다.
- 제한은 PySide6/Nuitka/pydantic native extension을 묶는 macOS 앱 패키징에만 적용한다.

## 다음 작업

- 없음.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/setup.ko.md`, `docs/setup.md`
