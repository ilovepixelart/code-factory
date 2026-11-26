"""The module's registration: its service resolves its ports from the registry at call time."""

import pytest

from code_factory.platform.background import BackgroundTasks
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine
from code_factory.platform.errors import UnavailableError
from code_factory.platform.module import Resources
from code_factory.platform.services import Services
from code_factory.team.module import module
from code_factory.team.service import (
    RunSource,
    TeamService,
)
from code_factory.tickets.models import Ticket
from team_fakes import Fakes


async def test_a_call_needs_only_the_ports_it_reads(
    offline_settings: Settings, uow: UnitOfWork, ticket: Ticket
) -> None:
    services = Services()
    assert module.provide is not None
    module.provide(
        services,
        Resources(offline_settings, create_engine(offline_settings), uow, BackgroundTasks()),
    )
    team = services.get(TeamService)
    assert await team.claim(ticket.id, "runner:a") is True  # no port read
    assert [view.agent for view in await team.list_claims()] == ["runner:a"]
    fakes = Fakes()
    services.add(RunSource, fakes.runs)
    await team.attach_run(ticket.id, "r1")
    assert await team.busy() == {"runner:a": ticket.id}  # reads the runs, which are registered
    with pytest.raises(UnavailableError, match=r"no service is registered for AgentSource"):
        await team.doing()


async def test_the_module_starts_the_keeper_when_the_app_starts(
    offline_settings: Settings, uow: UnitOfWork
) -> None:
    services = Services()
    tasks = BackgroundTasks()
    assert module.provide is not None
    assert module.background is not None
    module.provide(
        services, Resources(offline_settings, create_engine(offline_settings), uow, tasks)
    )
    async with tasks.run():
        module.background(services, tasks)
        assert tasks.names == ["team-keeper"]
