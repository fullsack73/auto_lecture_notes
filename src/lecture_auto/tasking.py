from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Callable


class TaskCancelledError(RuntimeError):
    """Raised when a cooperative background task is canceled."""


@dataclass(frozen=True)
class TaskEvent:
    job_id: str
    session_id: str | None
    stage: str
    completed: int | None = None
    total: int | None = None
    message: str = ""


ProgressCallback = Callable[[TaskEvent], None]


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise TaskCancelledError("Task was canceled.")


def report_progress(
    callback: ProgressCallback | None,
    *,
    job_id: str,
    session_id: str | None,
    stage: str,
    completed: int | None = None,
    total: int | None = None,
    message: str = "",
) -> None:
    if callback is not None:
        callback(
            TaskEvent(
                job_id=job_id,
                session_id=session_id,
                stage=stage,
                completed=completed,
                total=total,
                message=message,
            )
        )
