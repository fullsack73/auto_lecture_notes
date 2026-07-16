# 작업 기록 - 데스크톱 로컬 빌드 안내

- 일시: 2026-07-16 21:07 (KST)
- 작성자: Lecture Auto contributors
- 에이전트: Codex
- 작업 유형: 문서화

## 요약

- GitHub Release, Developer ID 서명, Apple 공증 자동화 방향을 철회하고 해당 작업 변경을 모두 원상 복구했다.
- 사용자가 Apple Silicon Mac에서 명령어로 앱을 직접 빌드하고 설치하는 절차를 사용자 문서에 추가했다.

## 변경 범위

- README와 한글/영문 setup의 로컬 macOS 빌드 안내
- desktop build 운영 문서
- 기술 스펙과 제품 제공 방식

## 주요 변경 파일

- `README.md`
- `docs/README.ko.md`
- `docs/setup.md`
- `docs/setup.ko.md`
- `deployment/README.md`
- `docs/02-specs.md`
- `docs/03-product-plan.md`

## 검증

- 기존 `scripts/build_macos_app.sh --install` 로컬 ARM64 빌드 경로와 문서 명령 일치 확인
- Markdown diff와 저장소 상태 확인

## 리스크/이슈

- 로컬 빌드 앱은 ad-hoc 서명만 사용하며 Developer ID 서명·Apple 공증 배포본이 아니다.
- 현재 빌드 스크립트는 native Apple Silicon 환경만 지원한다.

## 다음 작업

- 없음

## 참고

- 관련 문서: `deployment/README.md`, `docs/setup.ko.md`
