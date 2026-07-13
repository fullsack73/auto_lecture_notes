from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from lecture_auto.tasking import CancellationToken, TaskEvent


JobCallable = Callable[[CancellationToken, Callable[[TaskEvent], None], str], Any]


class WorkerSignals(QObject):
    progress = Signal(object)
    succeeded = Signal(str, object)
    failed = Signal(str, object)
    finished = Signal(str, object)


class Worker(QRunnable):
    def __init__(self, job_id: str, work: JobCallable, token: CancellationToken) -> None:
        super().__init__()
        self.job_id = job_id
        self.work = work
        self.token = token
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.token.raise_if_cancelled()
            self.signals.progress.emit(TaskEvent(self.job_id, None, "starting", 0, None, "Starting task."))
            result = self.work(self.token, self.signals.progress.emit, self.job_id)
            self.token.raise_if_cancelled()
            self.signals.progress.emit(TaskEvent(self.job_id, None, "complete", 1, 1, "Task complete."))
        except BaseException as exc:
            self.signals.failed.emit(self.job_id, exc)
        else:
            self.signals.succeeded.emit(self.job_id, result)


class JobController(QObject):
    progress = Signal(object)
    succeeded = Signal(str, object)
    failed = Signal(str, object)
    active_changed = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self._tokens: dict[str, CancellationToken] = {}
        self._sessions: dict[str, str | None] = {}
        self._blocks_close: dict[str, bool] = {}
        self._workers: dict[str, Worker] = {}

    @property
    def active_count(self) -> int:
        return len(self._tokens)

    @property
    def has_close_blocking_jobs(self) -> bool:
        return any(self._blocks_close.values())

    def is_session_busy(self, session_id: str) -> bool:
        return session_id in self._sessions.values()

    def submit(
        self,
        work: JobCallable,
        *,
        session_id: str | None = None,
        block_close: bool = True,
    ) -> str:
        if session_id and self.is_session_busy(session_id):
            raise RuntimeError(f"Session '{session_id}' already has an active task.")
        job_id = uuid.uuid4().hex
        token = CancellationToken()
        worker = Worker(job_id, work, token)
        worker.signals.progress.connect(self.progress)
        worker.signals.succeeded.connect(self.succeeded)
        worker.signals.failed.connect(self.failed)
        worker.signals.succeeded.connect(self._finish)
        worker.signals.failed.connect(self._finish)
        self._tokens[job_id] = token
        self._sessions[job_id] = session_id
        self._blocks_close[job_id] = block_close
        self._workers[job_id] = worker
        self.active_changed.emit(self.active_count)
        self.pool.start(worker)
        return job_id

    def cancel(self, job_id: str) -> None:
        token = self._tokens.get(job_id)
        if token:
            token.cancel()

    def cancel_all(self) -> None:
        for token in self._tokens.values():
            token.cancel()

    @Slot(str, object)
    def _finish(self, job_id: str, _result: object) -> None:
        self._tokens.pop(job_id, None)
        self._sessions.pop(job_id, None)
        self._blocks_close.pop(job_id, None)
        self._workers.pop(job_id, None)
        self.active_changed.emit(self.active_count)
