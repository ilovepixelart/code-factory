"""What every use case of the service shares."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from code_factory.metrics.adapters import GitReader
from code_factory.metrics.models import TrackedRepo
from code_factory.metrics.ports import MetricsPorts
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import NotFoundError

DAY = 86400.0


def utc_now() -> datetime:
    """The current time, timezone aware."""
    return datetime.now(UTC)


def instant(seconds: float) -> datetime:
    """An epoch time as an aware datetime."""
    return datetime.fromtimestamp(seconds, UTC)


@dataclass(frozen=True)
class Deps:
    """The unit of work, the four ports, the git reader and the clock."""

    uow: UnitOfWork
    ports: MetricsPorts
    git: GitReader
    now: Callable[[], datetime]

    def seconds(self) -> float:
        """The clock in epoch seconds."""
        return self.now().timestamp()

    async def repositories(self, name: str | None = None) -> list[TrackedRepo]:
        """Every tracked repository, or the one `name` names (`NotFoundError` when it is not)."""
        tracked = await self.ports.repositories.tracked()
        if name is None:
            return tracked
        chosen = [r for r in tracked if r.name == name]
        if not chosen:
            msg = f"{name} is not a tracked repository; track it first"
            raise NotFoundError(msg)
        return chosen
