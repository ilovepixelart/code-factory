"""What the sessions fixtures hand out: a clock to move and services that really commit."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sessions_values import NOW

from code_factory.platform.db import AsyncEngine
from code_factory.sessions.service import SessionService

TABLES = (
    "session_events",
    "session_rejects",
    "session_spool_progress",
    "session_views",
    "session_run_requests",
)


@dataclass(frozen=True, slots=True)
class Committed:
    """Builds services that commit for real, and an engine to look at what they wrote."""

    make: Callable[..., SessionService]
    admin: AsyncEngine
    # What the listeners of this schema call their connections.
    listener_name: str


class Clock:
    """A moment the test moves."""

    def __init__(self, seconds: float = NOW) -> None:
        self.seconds = seconds

    def __call__(self) -> datetime:
        return datetime.fromtimestamp(self.seconds, UTC)
