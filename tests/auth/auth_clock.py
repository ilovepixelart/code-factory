from datetime import UTC, datetime, timedelta

START = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


class Clock:
    """A clock the test moves."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: timedelta) -> None:
        self.now += by
