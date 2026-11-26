"""What the service parts share."""

from collections.abc import Callable
from datetime import UTC, datetime

type Clock = Callable[[], datetime]

STREAM_BATCH = 1000


def utc_now() -> datetime:
    """The current moment, in UTC."""
    return datetime.now(UTC)
