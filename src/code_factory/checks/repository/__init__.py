"""The checks module's queries: one store over a session."""

from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.checks.repository.records import RecordStore
from code_factory.checks.repository.remote import RemoteStore
from code_factory.checks.repository.runs import RunStore


class CheckStore:
    """Runs, runners and records over one session."""

    def __init__(self, session: AsyncSession) -> None:
        self.runs = RunStore(session)
        self.remote = RemoteStore(session)
        self.records = RecordStore(session)


__all__ = ["CheckStore"]
