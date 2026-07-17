# 작업 기록 - Windows uv Python 링크 우회

- 일시: 2026-07-17 18:34 (Asia/Seoul)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 버그 수정

## 요약

- Windows에서 Whisper add-on 설치 중 `uv python install`이 Python minor-version junction 생성 단계에서 OS 오류 448로 끝나도, 이미 내려받힌 실제 Python 3.11 설치를 찾아 계속 진행하도록 수정했다.
- 기존 concrete Python 3.11 설치가 있으면 junction을 다시 건드리지 않고 재사용한다.
- 임시 runtime 생성 시 `3.11` 별칭 대신 찾은 concrete Python 실행파일을 명시한다.
- `uv venv`가 다시 minor-version junction을 `pyvenv.cfg`에 기록해 패키지 설치 단계에서 오류 448을 일으키는 문제를 확인하고, concrete Python의 표준 `venv` 모듈로 runtime을 생성하도록 변경했다.
- add-on Python 3.11이 앱 번들의 Python 3.12 native module을 잘못 읽지 않도록 worker를 isolated UTF-8 mode로 실행하고 worker 디렉터리를 import 경로에서 제거한다.
- `google.genai`의 parent package가 없을 때 runtime probe가 중단되지 않고 미설치 상태를 반환하도록 수정했다.

## 변경 범위

- 관리형 Python 3.11 concrete 설치 탐지 및 최신 patch 선택
- Windows minor-version link 오류 복구 흐름
- 기존 설치 재사용과 신규 다운로드 후 링크 오류 회귀 테스트
- staging venv가 concrete Python 실행파일로 생성되는지 확인하는 회귀 테스트
- add-on worker Python 격리와 nested module 미설치 probe 처리

## 주요 변경 파일

- `src/lecture_auto/local_runtime.py`
- `src/lecture_auto/local_ai_worker.py`
- `src/lecture_auto/gemini_addon_worker.py`
- `tests/test_local_runtime.py`
- `tests/test_local_ai_worker.py`

## 검증

- 실제 사용자 runtime에서 `cpython-3.11.15-windows-x86_64-none/python.exe` 탐지 확인
- 실제 사용자 runtime에 `faster-whisper 1.2.1` 설치 및 `healthy=True` 확인
- 실제 사용자 runtime의 `pyvenv.cfg`가 `cpython-3.11.15-windows-x86_64-none` concrete 경로를 기록하는지 확인
- 현재 설치본 worker로 active runtime probe 성공 확인
- `.\.venv\Scripts\python.exe -m pytest -q tests\test_local_runtime.py tests\test_local_ai_worker.py`: 18 passed
- `.\.venv\Scripts\python.exe -m pytest -q`: 285 passed, 2 existing warnings
- `.\.venv\Scripts\lecture-auto.exe --help`: 정상
- 기존 Windows bundle lightweight verification 및 GUI smoke test: 정상
- 최종 수정 소스로 Windows x86_64 standalone 재빌드: 474,878,493 bytes, GUI smoke test 정상
- Inno Setup installer 재빌드: 131,037,220 bytes
- installer SHA-256: `A291361E5810CF482A66F2AE4B5F6FD31D4E67167DDF49C15928864667BD94B4`
- 빌드된 실행파일에서 junction fallback 문자열과 격리 worker 코드 포함 확인
- 빌드된 worker로 실제 active Whisper runtime probe 성공
- `git diff --check`: 정상

## 리스크/이슈

- concrete Python 실행파일이 손상된 경우 다음 venv 생성 단계에서 설치 오류로 처리된다.
- Windows installer는 공개 코드 서명이 적용되지 않았다.

## 다음 작업

- 별도 깨끗한 Windows 사용자 프로필에서 installer 설치 후 Whisper 최초 설치를 확인한다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/reports/260717-0352-03-windows-uv-link-retry.md`
- uv Python 설치 문서: <https://docs.astral.sh/uv/concepts/python-versions/>
