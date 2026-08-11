# 3) Lecture Auto 제품 계획

이 문서는 Lecture Auto의 제품 목적, 사용자, 핵심 흐름과 현재 범위를 정의한다. 구현 세부사항은 `docs/02-specs.md`, 사용자 설치/사용법은 `docs/README.ko.md`와 `docs/setup.ko.md`가 담당한다.

## A. 서비스 개요

### 목적

컴퓨터가 수업을 대신 듣도록 하여 사용자가 강의 중 필기 부담을 줄이고, 녹음부터 복습 가능한 구조화 노트까지의 흐름을 자동화한다.

핵심 파이프라인은 다음과 같다.

```text
세션 생성 → 강의 녹음 → STT 전사 → 전사문 정제 → 구조화 노트 생성 → library에서 복습
```

### 대상 사용자

- 강의를 놓치지 않고 나중에 복습하려는 학생
- 여러 수업의 녹음/전사/자료를 세션 단위로 관리하려는 학습자
- API provider와 로컬 AI를 상황에 맞게 선택하려는 개인 사용자

## B. 사용자 접점

### CLI

반복 작업, 스크립트, 자동화에 사용한다. 세션/녹음/전사/요약/library/config 명령과 JSON 출력이 핵심이다.

### TUI

터미널에서 세션 선택과 전체 파이프라인을 대화형으로 수행한다. 세션 관리, 오디오 관리, 전사 정제, 요약, library, 설정 메뉴를 제공한다.

### Desktop GUI

PySide6 기반으로 같은 workspace와 세션 데이터를 공유한다. 세션 관리, 녹음, 자료 import, 오디오 정제, 전사, 정제, 노트, library, 설정과 로컬 모델 관리를 제공한다. 설정 변경은 별도 저장 버튼 없이 자동 적용하고 저장 상태를 화면 상단에 표시한다.

## C. 핵심 기능 범위

### 세션과 자료

- session ID, 날짜, 제목, course를 가진 세션 생성/수정/삭제
- 세션별 metadata와 상태 관리
- PDF/PPT/PPTX 수업 자료 import; PPT/PPTX는 가능한 경우 PDF로 변환

### 녹음과 오디오

- 마이크 또는 시스템 오디오 녹음
- macOS AVFoundation, Windows DirectShow, Linux PulseAudio/ALSA 기반 FFmpeg 녹음과 플랫폼별 loopback/monitor 장치 지원
- 볼륨 정규화와 선택적 DeepFilterNet noise reduction

### 전사와 정제

- Deepgram/OpenAI-compatible API STT
- local Whisper/faster-whisper STT
- local device/compute/batch/VAD/beam과 용어 hotword 설정
- session/material glossary biasing과 제한된 저신뢰 구간 고품질 재전사
- warm local worker, 하드웨어 profile, 조건부 오디오 후보 비교
- raw transcript 생성
- timestamp/confidence/runtime을 담은 raw STT sidecar 생성
- LLM으로 오탈자/띄어쓰기/표현을 다듬되 의미와 용어를 보존하는 edited transcript 생성
- refine evidence와 숫자·고유명사 변경 audit sidecar

### 노트와 library

- transcript와 선택적 수업 자료 context를 바탕으로 구조화 강의 노트 생성
- transcript의 중심 주제를 반영한 내용 기반 노트 제목 생성
- `Topic Overview`, `Core Concepts`, `Detailed Explanations`, `Examples Mentioned`, `Questions to Review`, `Exam related mentions` 섹션 유지
- 세션, 노트, 전사문, 녹음 파일 검색/목록/열기

## D. Provider 선택

| 영역 | API/외부 | 로컬 |
| --- | --- | --- |
| STT | Deepgram, OpenAI-compatible | Whisper/faster-whisper |
| LLM | Gemini/Gemma Google API | Ollama |

로컬 STT 기본 provider는 faster-whisper다. whisper.cpp/MLX, SenseVoiceSmall,
Qwen3-ASR-0.6B, Moonshine 한국어 모델은 backend·모델·라이선스·패키징이 분리된
benchmark 후보이며 검증 없이 사용자 기본값으로 자동 선택하지 않는다.

외부 API와 로컬 모델은 동일한 세션 workflow를 공유하되, 인증·설치·성능·비용 조건은 provider별로 다르다.

## E. 현재 제품 원칙과 비범위

- 노트는 한 가지 `structured-notes` 형식으로 통일한다. 임의 Markdown 템플릿 선택 기능을 늘리지 않는다.
- API key는 사용자 설정에 보관하되 저장소나 일반 config JSON에 평문으로 남기지 않는다.
- CLI/TUI/GUI는 같은 workspace와 metadata를 사용해야 한다.
- 현재 범위는 개인 학습용 로컬 앱이다. 다중 사용자 계정, 서버 동기화, 협업 편집, 모바일 앱, 실시간 자막 UI는 제품 범위에 포함하지 않는다.
- 녹음 권한, loopback/monitor device, provider key/model 설치는 실행 환경의 책임이다. macOS/Windows/Linux 데스크톱 빌드는 검증된 FFmpeg/FFprobe를 포함하지만 개발용 CLI는 해당 도구를 별도로 준비할 수 있다.
- 데스크톱 앱은 각 운영체제에서 네이티브로 로컬 빌드할 수 있다. 버전별 GitHub Release는 Windows x86_64 installer와 Linux x86_64 AppImage/portable archive를 제공하며, 현재 플랫폼 배포 인증서로 서명하지 않는다.

## F. 완료 기준

기능 변경은 다음 조건을 만족할 때 제품 범위에 들어온 것으로 본다.

- 정상 흐름과 실패 흐름이 `SessionService` 또는 관련 서비스에서 일관되게 처리된다.
- CLI/TUI/GUI 중 영향을 받는 사용자 접점이 같은 업무 규칙을 사용한다.
- workspace 산출물과 기존 세션 데이터의 호환성을 확인한다.
- 관련 자동화 테스트와 사용자 문서 또는 운영 문서를 갱신한다.
