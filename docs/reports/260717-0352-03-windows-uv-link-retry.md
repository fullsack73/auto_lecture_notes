# 작업 기록 - Windows uv Python 링크 재시도

- 일시: 2026-07-17 03:52 (Asia/Seoul)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 버그 수정

## 요약

- Windows에서 Whisper add-on 최초 설치 중 `uv python install`이 Python minor-version junction 생성 후 OS 오류 448로 종료되는 문제를 수정했다.
- 해당 Windows 링크 오류에 한해 같은 명령을 자동으로 한 번 재시도하며, 네트워크 오류 등 다른 실패는 재시도하지 않고 그대로 전달한다.
- 새 Windows standalone 앱과 Inno Setup 설치 프로그램을 생성했다.

## 변경 범위

- 관리형 Python 준비 단계의 Windows 전용 복구 동작
- 오류 448 재시도 및 일반 오류 비재시도 테스트

## 주요 변경 파일

- `src/lecture_auto/local_runtime.py`
- `tests/test_local_runtime.py`
- `dist-installer/LectureAuto-Setup.exe` (빌드 산출물, 저장소 추적 제외)

## 검증

- 실제 실패 runtime에서 동일 `uv python install` 재실행 성공
- 별도 깨끗한 설치 경로에서 CPython 3.11.15 설치 및 Windows junction 생성 성공
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_local_runtime.py`: 14 passed
- `.\.venv\Scripts\python.exe -m pytest -q`: 281 passed, 2 warnings
- `.\scripts\build_windows_app.ps1`: Windows standalone 빌드 및 GUI smoke test 통과
- `.\scripts\build_windows_app.ps1 -InstallerOnly`: Inno Setup installer 생성 성공
- 설치 프로그램 SHA-256: `DB24E6B5E348EE269D6FB6309ED053CB13A49730F78CB5C6FBA202C32D5AC8A8`

## 리스크/이슈

- 자동 재시도는 Windows 오류 448 또는 `minor version link directory` 오류에만 적용한다.
- 두 번째 시도도 실패하면 원래와 동일하게 설치를 중단하고 오류를 표시한다.
- 설치 프로그램은 공개 배포용 코드 서명이 적용되지 않았다.

## 다음 작업

- 실행 중인 Lecture Auto를 종료하고 새 설치 프로그램으로 덮어쓴 뒤 Whisper add-on 설치를 다시 실행한다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/reports/260717-0342-02-windows-whisper-utf8.md`
- uv Python 관리 문서: <https://docs.astral.sh/uv/concepts/python-versions/>
