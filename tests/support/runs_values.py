"""Builders the runs tests share: a frozen clock and runs of a ticket."""

from datetime import UTC, datetime, timedelta

from code_factory.runs.models import Run

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
OWNER = "owner"


def at(seconds: float) -> datetime:
    """`seconds` after NOW (before it when negative)."""
    return NOW + timedelta(seconds=seconds)


def a_run(number: int | None, run_id: str = "a1b2c3d4e5f6", **fields: object) -> Run:
    """A build run of ticket `number` (the coordinator's when None), active unless told."""
    base: dict[str, object] = {
        "id": run_id,
        "ticket_id": number,
        "ticket_key": "coordinator" if number is None else f"CF-{number}",
        "repository": "sample",
        "stage": "build",
        "started_at": NOW,
    }
    return Run(**(base | fields))  # ty: ignore[invalid-argument-type]


class FakeClock:
    """A settable clock the service reads as a `datetime`."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self.now += timedelta(seconds=seconds)
