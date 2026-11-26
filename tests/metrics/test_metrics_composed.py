"""The metrics of the composed app read the real runs and checks: rows the test writes show."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app_lifespan import IDLE_MODULES
from code_factory.app import build_services
from code_factory.checks.service import CheckService
from code_factory.metrics.models import CheckRecord
from code_factory.metrics.module import ChecksAdapter, RunsAdapter
from code_factory.metrics.service import MetricsService
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine
from code_factory.platform.module import Resources
from code_factory.platform.services import Services
from code_factory.runs.repository import RunRepository
from code_factory.tickets.models import Ticket
from code_factory.tickets.service import TicketService
from runs_values import a_run
from ticket_values import NOW as TICKETS_NOW

COMMIT = "c" * 40


@pytest.fixture
def services(settings: Settings, uow: UnitOfWork) -> Services:
    resources = Resources(settings, create_engine(settings), uow, BackgroundTasks())
    return build_services(resources, IDLE_MODULES)


async def test_the_flow_agents_table_counts_a_recorded_run_and_its_cost(
    services: Services, db_session: AsyncSession, ticket: Ticket
) -> None:
    started = datetime.now(UTC) - timedelta(hours=1)
    await RunRepository(db_session).insert(
        a_run(
            ticket.number, agent="writer", model="m-1", started_at=started, exit_code=0,
            ended_at=started + timedelta(minutes=5), tokens=1200, cost=0.5,
        )
    )  # fmt: skip

    page = await services.get(MetricsService).flow("7d")

    [row] = page.agents
    assert (row.agent, row.model, row.runs, row.finished, row.tokens, row.cost) == (
        "writer", "m-1", 1, 1, 1200, 0.5,
    )  # fmt: skip


async def test_the_build_starts_are_the_first_build_run_of_each_ticket(
    services: Services, db_session: AsyncSession, ticket: Ticket
) -> None:
    first = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    repo = RunRepository(db_session)
    await repo.insert(a_run(ticket.number, "run-1", started_at=first, exit_code=0))
    await repo.insert(a_run(ticket.number, "run-2", started_at=first + timedelta(hours=2)))
    await repo.insert(a_run(ticket.number, "run-3", stage="review", started_at=first, exit_code=0))

    starts = await RunsAdapter(services).build_starts(
        "sample", first - timedelta(days=1), first + timedelta(days=1)
    )

    assert starts == {ticket.id: first}


async def test_a_checks_record_is_read_as_the_verdict_and_the_step_times(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    data: dict[str, object] = {
        "commit": COMMIT, "exit_code": 1, "seconds": {"lint": 3},
        "steps": {"lint": "passed", "tests": "failed"},
    }  # fmt: skip
    await tickets.record_activity(ticket.id, "checks", data, by="board")
    adapter = ChecksAdapter(services.get(CheckService))

    assert await adapter.records("sample", [ticket.id]) == [
        CheckRecord(ticket_id=ticket.id, commit=COMMIT, exit_code=1, at=TICKETS_NOW)
    ]
    assert await adapter.records("other", [ticket.id]) == []
    steps = {s.step: s.runs for s in await services.get(MetricsService).step_times()}
    assert steps == {"lint": 1, "tests": 1}
