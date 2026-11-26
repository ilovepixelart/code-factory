"""Values the talk tests share: a clock the test moves, and the actors."""

from datetime import UTC, datetime, timedelta

START = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)
OWNER = "owner"
RUN = "run-1"


class Clock:
    """A clock that stands still until a test advances it."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> datetime:
        self.now += timedelta(**delta)
        return self.now
