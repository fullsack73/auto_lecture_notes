# 작업 기록 - Austin Docs Architecture 적용

- 일시: 2026-07-13 21:42 (KST)
- 작성자: 사용자
- 에이전트: Codex
- 작업 유형: 문서화

## 요약

- `EunHyeokJung/austin-docs-architecture`의 한국어 docs-first 운영 구조를 Lecture Auto에 적용했다.
- 템플릿의 예시 내용을 현재 Python CLI/TUI/Desktop GUI 프로젝트의 실제 구조와 workflow로 교체했다.

## 변경 범위

- 에이전트 공통 규칙과 작업 전 필독 문서 추가
- 폴더 책임, 계층 의존성, workspace 산출물 구조 문서화
- Python runtime, provider adapter, 보안, CLI 호환성, 검증 규칙 문서화
- 제품 목적, 사용자 흐름, provider 범위, 비범위 문서화
- TODO/작업 기록 운영 폴더와 템플릿 추가
- README에 문서 체계 링크 추가

## 주요 변경 파일

- `AGENTS.md`
- `docs/01-folder-architecture.md`
- `docs/02-specs.md`
- `docs/03-product-plan.md`
- `docs/todo/00-todo-list.md`
- `docs/todo/_template.md`
- `docs/reports/_template.md`
- `README.md`

## 검증

- 템플릿 예시 문구/placeholder 검색 결과 없음
- `git diff --check` 통과
- `.venv/bin/pytest -q` 결과: `258 passed`, 기존 Ollama 테스트 경고 2건
- `.venv/bin/lecture-auto --help` 통과
- 기존 `docs/README*.md`, `docs/setup*.md`는 보존
- `scripts/verify_lightweight_app.py`는 현재 진행 중인 Nuitka 빌드의 빈 앱 번들 때문에 실행 파일 검증 불가

## 리스크/이슈

- 문서 구조 적용만 포함하며, 코드 동작 변경은 없다.

## 다음 작업

- 이후 기능 작업부터 `AGENTS.md`의 필독 문서와 TODO/report workflow를 사용한다.

## 참고

- 원본: https://github.com/EunHyeokJung/austin-docs-architecture
