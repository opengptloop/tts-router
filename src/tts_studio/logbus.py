"""In-memory log ring buffer with WebSocket fan-out.

Every log record goes through :class:`LogBus` so the frontend can display
live logs on the Config page and machine logs can be tailed over REST.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogRecord:
    seq: int
    ts: float
    level: str
    logger: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "time": time.strftime("%H:%M:%S", time.localtime(self.ts)),
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
        }


class LogBus:
    """Thread-safe ring buffer of log records with async subscribers."""

    def __init__(self, capacity: int = 4000) -> None:
        self._records: deque[LogRecord] = deque(maxlen=capacity)
        self._seq = 0
        self._lock = threading.Lock()
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- lifecycle ---------------------------------------------------------
    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # -- writing -----------------------------------------------------------
    def append(self, level: str, logger: str, message: str) -> LogRecord:
        with self._lock:
            self._seq += 1
            record = LogRecord(
                seq=self._seq,
                ts=time.time(),
                level=level,
                logger=logger,
                message=message,
            )
            self._records.append(record)
            subscribers = list(self._subscribers)
        loop = self._loop
        if loop is not None and subscribers:
            for queue in subscribers:
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, record)
                except RuntimeError:
                    pass
        return record

    def log(self, level: str, logger: str, message: str) -> None:
        self.append(level, logger, message)

    # -- reading -----------------------------------------------------------
    def tail(self, after_seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            records = [r for r in self._records if r.seq > after_seq]
            records = records[-limit:]
        return [r.as_dict() for r in records]

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    # -- subscriptions -----------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)


BUS = LogBus()


class BusLogHandler(logging.Handler):
    """Logging handler that forwards records into the shared LogBus."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover - defensive
            message = record.getMessage()
        BUS.append(record.levelname, record.name, message)


_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging to console + file + LogBus (idempotent)."""
    global _configured
    if _configured:
        return
    _configured = True

    from . import config

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.FileHandler(config.LOGS_DIR / "tts-studio.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    bus_handler = BusLogHandler()
    bus_handler.setFormatter(logging.Formatter("%(message)s"))
    bus_handler.setLevel(logging.INFO)
    root.addHandler(bus_handler)

    # Quieten noisy third-party loggers a little.
    for noisy in ("httpx", "httpcore", "urllib3", "filelock", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
