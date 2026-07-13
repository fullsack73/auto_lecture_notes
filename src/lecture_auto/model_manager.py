from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from lecture_auto.tasking import CancellationToken
from lecture_auto.local_runtime import LocalRuntimeManager


ModelProgressCallback = Callable[[str, int | None, int | None], None]


@dataclass(frozen=True)
class LocalModel:
    name: str
    provider: str
    installed: bool
    path: str | None = None
    size_bytes: int | None = None


def default_model_dir() -> Path:
    override = os.environ.get("LECTURE_AUTO_MODEL_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "Lecture Auto"
    elif sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Lecture Auto"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lecture-auto"
    return root / "models"


class ModelManager:
    WHISPER_MODELS = ("base", "small", "medium", "large-v3")

    def __init__(
        self,
        model_dir: Path | None = None,
        ollama_base_url: str = "http://localhost:11434",
        local_runtime_manager: LocalRuntimeManager | None = None,
    ) -> None:
        self.model_dir = Path(model_dir or default_model_dir())
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.local_runtime_manager = local_runtime_manager or LocalRuntimeManager()

    def list_whisper_models(self) -> list[LocalModel]:
        return [self.whisper_status(name) for name in self.WHISPER_MODELS]

    def whisper_status(self, name: str) -> LocalModel:
        path = self.model_dir / "whisper" / name
        marker = self.model_dir / "whisper" / f"{name}.installed.json"
        installed = marker.is_file() or (path.is_dir() and any(path.iterdir()))
        return LocalModel(
            name=name,
            provider="faster-whisper",
            installed=installed,
            path=str(path if path.exists() else self.model_dir / "whisper") if installed else None,
            size_bytes=self._directory_size(self.model_dir / "whisper") if installed else None,
        )

    def install_whisper(
        self,
        name: str,
        *,
        progress: ModelProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> LocalModel:
        if not name.strip():
            raise ValueError("Whisper model name is required.")
        token = cancellation_token or CancellationToken()
        token.raise_if_cancelled()
        target = self.model_dir / "whisper"
        target.mkdir(parents=True, exist_ok=True)
        if progress:
            progress("downloading", 0, None)
        def runtime_progress(stage: str, completed: int | float | None, total: int | float | None, _message: str) -> None:
            if progress:
                progress(stage, int(completed) if isinstance(completed, int) else None, int(total) if isinstance(total, int) else None)

        self.local_runtime_manager.run_feature(
            "whisper",
            {
                "action": "download_whisper_model",
                "model": name,
                "download_root": str(target),
            },
            progress=runtime_progress,
            cancellation_token=token,
            timeout=None,
        )
        marker = target / f"{name}.installed.json"
        marker.write_text('{"installed":true}', encoding="utf-8")
        token.raise_if_cancelled()
        if progress:
            progress("complete", 1, 1)
        return self.whisper_status(name)

    def delete_whisper(self, name: str) -> None:
        shutil.rmtree(self.model_dir / "whisper" / name, ignore_errors=True)
        (self.model_dir / "whisper" / f"{name}.installed.json").unlink(missing_ok=True)

    def ollama_health(self) -> bool:
        try:
            client = self._ollama_client()
            client.list()
            return True
        except Exception:
            return False

    def list_ollama_models(self) -> list[str]:
        response = self._ollama_client().list()
        models: Iterable[Any]
        if isinstance(response, dict):
            models = response.get("models", [])
        else:
            models = getattr(response, "models", [])
        names: list[str] = []
        for model in models:
            if isinstance(model, dict):
                value = model.get("model") or model.get("name")
            else:
                value = getattr(model, "model", None) or getattr(model, "name", None)
            if value:
                names.append(str(value))
        return names

    def pull_ollama(
        self,
        name: str,
        *,
        progress: ModelProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        token = cancellation_token or CancellationToken()
        for part in self._ollama_client().pull(name, stream=True):
            token.raise_if_cancelled()
            if isinstance(part, dict):
                status = str(part.get("status", "downloading"))
                completed = part.get("completed")
                total = part.get("total")
            else:
                status = str(getattr(part, "status", "downloading"))
                completed = getattr(part, "completed", None)
                total = getattr(part, "total", None)
            if progress:
                progress(status, completed, total)

    def delete_ollama(self, name: str) -> None:
        self._ollama_client().delete(name)

    def _ollama_client(self):
        try:
            import ollama
        except ImportError as exc:
            raise RuntimeError("ollama Python package is not installed.") from exc
        return ollama.Client(host=self.ollama_base_url)

    @staticmethod
    def _directory_size(path: Path) -> int:
        total = 0
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
        return total
