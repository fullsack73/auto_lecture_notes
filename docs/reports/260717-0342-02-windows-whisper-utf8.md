# 작업 기록 - Windows Whisper 설치 UTF-8 처리

- 일시: 2026-07-17 03:42 (Asia/Seoul)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 버그 수정

## 요약

- Windows GUI에서 Whisper add-on 설치 중 `uv`의 UTF-8 로그를 CP949로 해석해 발생하던 `UnicodeDecodeError`를 수정했다.
- add-on 설치 명령과 Python worker의 표준 입출력을 UTF-8로 고정하고, 한글 입출력 회귀 테스트를 추가했다.
- 수정된 Windows standalone 앱과 Inno Setup 설치 프로그램을 다시 생성했다.

## 변경 범위

- 로컬 AI runtime 설치 subprocess 출력 디코딩
- 로컬 AI worker JSONL 프로토콜 입출력 인코딩
- Windows Whisper 설치 한글 로그 회귀 테스트

## 주요 변경 파일

- `src/lecture_auto/local_runtime.py`
- `tests/test_local_runtime.py`
- `dist-installer/LectureAuto-Setup.exe` (빌드 산출물, 저장소 추적 제외)

## 검증

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_local_runtime.py`: 12 passed
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_gui_smoke.py tests/test_local_runtime.py`: 28 passed
- `.\.venv\Scripts\python.exe -m pytest -q`: 279 passed, 2 warnings
- `.\scripts\build_windows_app.ps1`: Windows standalone 빌드 및 GUI smoke test 통과
- `.\scripts\build_windows_app.ps1 -InstallerOnly`: Inno Setup installer 생성 성공
- 설치 프로그램 SHA-256: `9A833D0B4F27A5A3864CCEA141C3A5470AAEFE8EB0A84537A1DC172AFA3DA117`

## 리스크/이슈

- 설치 명령 출력에 UTF-8이 아닌 바이트가 섞이면 대체 문자로 표시하지만, 설치 프로세스 자체는 계속 진행한다.
- 설치 프로그램은 공개 배포용 코드 서명이 적용되지 않았다.

## 다음 작업

- 새 설치 프로그램으로 기존 앱을 덮어쓴 뒤 Whisper add-on 설치를 다시 실행한다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/reports/260717-0325-01-windows-linux-gui-build.md`
