"""Fixtures of the runs tests: the repositories over the isolated test database."""

import signal
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import UnitOfWork
from code_factory.runs.adapters import processes
from code_factory.runs.adapters.processes import ProcessRegistry
from code_factory.runs.ports import TicketFacts
from code_factory.runs.repository import RunRepository
from code_factory.runs.service import RunService
from code_factory.tickets.models import Ticket
from runs_fakes import Fakes
from runs_values import FakeClock


@pytest.fixture
def run_repo(db_session: AsyncSession) -> RunRepository:
    return RunRepository(db_session)


@pytest.fixture
def fakes(tmp_path: Path) -> Fakes:
    """Fake ports; a test sets what each answers and reads what each received."""
    return Fakes(tmp_path)


@pytest.fixture
async def registry() -> AsyncGenerator[ProcessRegistry]:
    """The process registry; every group it holds is ended at the end of the test."""
    held = ProcessRegistry(term_grace_s=0.3)
    yield held
    for pid in held.pids():
        processes.signal_group(pid, signal.SIGKILL)
    await held.reap_all()


@pytest.fixture
def clock() -> FakeClock:
    """The service's clock, at `runs_values.NOW` until a test moves it."""
    return FakeClock()


@pytest.fixture
def runs(
    uow: UnitOfWork, fakes: Fakes, registry: ProcessRegistry, tmp_path: Path, clock: FakeClock
) -> RunService:
    """The run service over the fake ports, the isolated database and a real process registry."""
    return RunService(uow, fakes.ports, registry, state_dir=tmp_path / "state", clock=clock)


@pytest.fixture
def facts(fakes: Fakes, ticket: Ticket) -> TicketFacts:
    """The `sample` ticket as the fake tickets port answers it."""
    found = TicketFacts(
        id=ticket.id, number=ticket.number, repository="sample", title="A ticket", kind="feature"
    )
    fakes.tickets.facts_by_id[ticket.id] = found
    return found
