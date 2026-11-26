"""Structured logging that never blocks the event loop.

Records go to a bounded queue; a listener thread formats and writes them. The request id travels
in a context variable and is stamped on every record by the record factory, so every handler
sees it.
"""

import json
import logging
import queue
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import QueueHandler, QueueListener
from typing import IO, Any, Self, override

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_QUEUE_SIZE = 10_000
_STANDARD_ATTRIBUTES = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}
_factory_installed = False


def install_record_factory() -> None:
    """Stamp `request_id` on every record created from now on. Idempotent."""
    global _factory_installed  # noqa: PLW0603  # the factory is process wide, installed once
    if _factory_installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:  # noqa: ANN401
        record = previous(*args, **kwargs)
        record.request_id = request_id_var.get()
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Render the record, its request id and any `extra` fields."""
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        payload |= {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_ATTRIBUTES and key != "request_id"
        }
        exc_info = record.exc_info
        if isinstance(exc_info, tuple) and exc_info[0] is not None:
            payload["exception"] = self.formatException(exc_info)
        return json.dumps(payload, default=str)


class LoggingHandle:
    """Owns the listener thread; `stop()` flushes the queue and removes the handler."""

    def __init__(self, handler: QueueHandler, listener: QueueListener) -> None:
        self._handler = handler
        self._listener = listener

    def stop(self) -> None:
        """Drain the queue, stop the thread and detach from the root logger."""
        logging.getLogger().removeHandler(self._handler)
        self._listener.stop()

    def __enter__(self) -> Self:
        """Use as a context manager that stops on exit."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Stop the listener."""
        self.stop()


def setup_logging(level: str = "INFO", stream: IO[str] | None = None) -> LoggingHandle:
    """Send the root logger through a queue to JSON lines on `stream` (stderr by default).

    Stdout stays free: `code-factory mcp` speaks the protocol on it.
    """
    install_record_factory()
    root = logging.getLogger()
    for existing in [h for h in root.handlers if isinstance(h, QueueHandler)]:
        root.removeHandler(existing)
    sink = logging.StreamHandler(stream if stream is not None else sys.stderr)
    records: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=_QUEUE_SIZE)
    handler = QueueHandler(records)
    # QueueHandler drops exc_info when it prepares a record, so the JSON (traceback included) is
    # rendered here, in the producer; the listener thread only writes the finished line.
    handler.setFormatter(JsonFormatter())
    listener = QueueListener(records, sink)
    root.addHandler(handler)
    root.setLevel(level)
    listener.start()
    return LoggingHandle(handler, listener)
