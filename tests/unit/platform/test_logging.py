import io
import json
import logging
import threading
from typing import override

from code_factory.platform.logging import request_id_var, setup_logging


def test_records_are_json_lines_stamped_with_the_request_id() -> None:
    stream = io.StringIO()
    with setup_logging("INFO", stream):
        token = request_id_var.set("req-42")
        try:
            logging.getLogger("t").info("hello %s", "world", extra={"path": "/x"})
        finally:
            request_id_var.reset(token)
        logging.getLogger("t").info("outside")
    first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    assert (first["message"], first["request_id"], first["path"]) == ("hello world", "req-42", "/x")
    assert first["level"] == "INFO"
    assert second["request_id"] is None


def test_an_exception_keeps_its_traceback_through_the_queue() -> None:
    stream = io.StringIO()
    with setup_logging("INFO", stream):
        try:
            raise ValueError("boom")  # noqa: TRY301
        except ValueError:
            logging.getLogger("t").exception("failed")
    record = json.loads(stream.getvalue())
    assert "ValueError: boom" in record["exception"]


def test_the_level_filters_records() -> None:
    stream = io.StringIO()
    with setup_logging("WARNING", stream):
        logging.getLogger("t").info("quiet")
        logging.getLogger("t").warning("loud")
    assert [json.loads(line)["message"] for line in stream.getvalue().splitlines()] == ["loud"]


class _ThreadRecordingStream(io.StringIO):
    """A sink that remembers which thread wrote to it."""

    def __init__(self) -> None:
        super().__init__()
        self.writers: set[str] = set()

    @override
    def write(self, text: str, /) -> int:
        self.writers.add(threading.current_thread().name)
        return super().write(text)


def test_records_are_written_by_the_listener_thread_not_the_logging_one() -> None:
    stream = _ThreadRecordingStream()
    with setup_logging("INFO", stream):
        logging.getLogger("t").info("from the caller")
    assert stream.writers
    assert threading.current_thread().name not in stream.writers
