# 작업 기록 - macOS 실행 중 앱 재설치 보호

- 일시: 2026-08-11 16:23 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 버그 수정

## 요약

- 실행 중인 `/Applications/Lecture Auto.app`을 삭제·복사한 뒤 LaunchServices가 기존 프로세스를 계속 재사용해 새 빌드가 열리지 않는 재설치 문제를 수정했다.
- 실행 중 앱은 빌드 전에 명확한 오류로 중단하고, 닫힌 앱은 staging 복사와 서명 검증 뒤 교체하도록 변경했다.
- macOS 빌드에 실제 GUI smoke launch 검증을 활성화했다.

## 변경 범위

- macOS 설치본 실행 프로세스 감지
- 기존 설치본을 보존하는 staging 기반 교체
- macOS 빌드 GUI smoke test 활성화
- 설치 회귀 테스트와 한·영 설치 문서

## 주요 변경 파일

- `scripts/build_macos_app.sh`
- `scripts/install_macos_app.py`
- `tests/test_install_macos_app.py`
- `docs/02-specs.md`
- `docs/setup.ko.md`, `docs/setup.md`

## 검증

- 실행 중 실제 설치본 PID 감지 및 빌드 전 종료 코드 4 확인
- 설치 helper 및 verifier 테스트 8개 통과
- 실제 `ditto`, `xattr`, `codesign`을 사용한 임시 기존 앱 교체 및 서명 검증 통과
- 패키징된 GUI smoke launch 통과
- 외부 Ollama 실서비스 테스트를 제외한 전체 테스트: 328 passed, 1 skipped
- zsh 및 Python 문법 검사 통과

## 리스크/이슈

- 설치 스크립트는 진행 중인 녹음이나 작업을 임의로 중단하지 않기 위해 앱을 자동 종료하지 않는다.
- 전체 `pytest -q`의 기존 Ollama 실서비스 테스트 3개는 로컬 Ollama 서버가 실행 중이지 않아 실패했다. 이번 변경과 무관한 외부 통합 테스트이며 나머지 328개는 통과했다.

## 다음 작업

- 없음.

## 참고

- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`, `docs/setup.ko.md`, `docs/setup.md`
