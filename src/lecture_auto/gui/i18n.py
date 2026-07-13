from __future__ import annotations


STRINGS = {
    "ko": {
        "app_title": "Lecture Auto",
        "home": "홈",
        "sessions": "세션",
        "library": "보관함",
        "settings": "설정",
        "new_session": "새 세션",
        "refresh": "새로고침",
        "save": "저장",
        "delete": "삭제",
        "cancel": "취소",
        "running": "작업 중",
        "ready": "준비됨",
    },
    "en": {
        "app_title": "Lecture Auto",
        "home": "Home",
        "sessions": "Sessions",
        "library": "Library",
        "settings": "Settings",
        "new_session": "New session",
        "refresh": "Refresh",
        "save": "Save",
        "delete": "Delete",
        "cancel": "Cancel",
        "running": "Running",
        "ready": "Ready",
    },
}


class Translator:
    def __init__(self, language: str = "ko") -> None:
        self.language = language if language in STRINGS else "ko"

    def __call__(self, key: str) -> str:
        return STRINGS[self.language].get(key, key)
