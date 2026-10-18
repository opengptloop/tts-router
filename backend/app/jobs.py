"""Background job manager.

Long running work (model loads, voice downloads, engine installs, speech
generation) runs in thread pools so the API stays responsive. Jobs report
progress and can be cancelled cooperatively through a threading event.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("tts.jobs")

MAX_JOBS = 300


class CancelledError(Exception):
    """Raised inside a job when cancellation was requested."""


@dataclass
class Job:
    id: str
    kind: str
    label: str
    status: str = "queued"  # queued | running | succeeded | failed | cancelled
    progress: float = 0.0  # 0..1 (negative means indeterminate)
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    logs: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_log(self, message: str, level: str = "INFO") -> None:
        with self._lock:
            self.logs.append(
                {"ts": time.time(), "level": level, "message": message}
            )
        getattr(logger, level.lower(), logger.info)(
            "[job %s/%s] %s", self.kind, self.id[:8], message
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "kind": self.kind,
                "label": self.label,
                "status": self.status,
                "progress": self.progress,
                "message": self.message,
                "result": self.result,
                "error": self.error,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "logs": list(self.logs),
            }


class JobContext:
    """Passed to job callables for progress / cancellation reporting."""

    def __init__(self, job: Job) -> None:
        self.job = job

    @property
    def cancelled(self) -> bool:
        return self.job.cancel_event.is_set()

    def is_cancelled(self) -> bool:
        """Callable form, for APIs that take a cancellation predicate."""
        return self.job.cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError("Job cancelled")

    def log(self, message: str, level: str = "INFO") -> None:
        self.job.add_log(message, level)

    def progress(self, fraction: float, message: str | None = None) -> None:
        with self.job._lock:
            self.job.progress = max(0.0, min(1.0, float(fraction)))
            if message:
                self.job.message = message

    def message(self, text: str) -> None:
        with self.job._lock:
            self.job.message = text


class JobManager:
    """Runs jobs in dedicated thread pools and tracks their state."""

    def __init__(self) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        # Generation and model loads share the compute pool: heavy torch work.
        self._compute = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="tts-compute"
        )
        # Downloads / pip installs run independently so they never block
        # behind a long generation.
        self._io = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tts-io")

    # -- API ---------------------------------------------------------------
    def submit(
        self,
        kind: str,
        label: str,
        fn: Callable[[JobContext], dict[str, Any] | None],
        pool: str = "compute",
    ) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind, label=label)
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > MAX_JOBS:
                self._jobs.popitem(last=False)
        executor = self._compute if pool == "compute" else self._io
        executor.submit(self._run, job, fn)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self, job_id: str) -> dict[str, Any] | None:
        job = self.get(job_id)
        return job.snapshot() if job else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())[-limit:]
        return [job.snapshot() for job in reversed(jobs)]

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.status in ("succeeded", "failed", "cancelled"):
            return False
        job.cancel_event.set()
        job.add_log("Cancellation requested", "WARNING")
        return True

    def shutdown(self) -> None:
        self._compute.shutdown(wait=False, cancel_futures=True)
        self._io.shutdown(wait=False, cancel_futures=True)

    # -- internals ---------------------------------------------------------
    def _run(
        self, job: Job, fn: Callable[[JobContext], dict[str, Any] | None]
    ) -> None:
        ctx = JobContext(job)
        with job._lock:
            job.status = "running"
            job.started_at = time.time()
        job.add_log(f"Started: {job.label}")
        try:
            if ctx.cancelled:
                raise CancelledError("Cancelled before start")
            result = fn(ctx)
            with job._lock:
                job.status = "succeeded"
                job.progress = 1.0
                job.result = result or None
            job.add_log("Finished")
        except CancelledError:
            with job._lock:
                job.status = "cancelled"
            job.add_log("Cancelled", "WARNING")
        except Exception as exc:  # noqa: BLE001 - report every failure to the UI
            with job._lock:
                job.status = "failed"
                job.error = str(exc) or exc.__class__.__name__
            job.add_log(f"Failed: {job.error}", "ERROR")
            logger.error("Job %s failed: %s", job.kind, exc)
            logger.debug(traceback.format_exc())
        finally:
            with job._lock:
                if job.finished_at is None:
                    job.finished_at = time.time()


JOBS = JobManager()
