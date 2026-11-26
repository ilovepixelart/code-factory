"""The module's registration: its service resolves its ports from the registry at call time."""

import pytest

from code_factory.app import MODULES, build_resources, build_services
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine
from code_factory.platform.errors import UnavailableError
from code_factory.platform.module import Resources
from code_factory.platform.services import Services
from code_factory.team.module import module
from code_factory.team.service import (
    AgentSource,
    GateSource,
    JobSource,
    OwnerSource,
    RunSource,
    SessionSource,
    TeamService,
    TicketSource,
)
from code_factory.tickets.models import Ticket
from team_fakes import Fakes


def test_the_module_is_listed_in_the_composition_root_with_its_command() -> None:
    assert module in MODULES
    assert [command.name for command in module.commands] == ["team"]


async def test_a_provider_that_registers_after_the_team_is_still_found(
    offline_settings: Settings,
) -> None:
    services = build_services(build_resources(offline_settings), [module])
    team = services.get(TeamService)
    with pytest.raises(UnavailableError, match=r"no service is registered for AgentSource"):
        await team.now()
    fakes = Fakes()
    for key, port in (
        (AgentSource, fakes.agents),
        (RunSource, fakes.runs),
        (TicketSource, fakes.tickets),
        (GateSource, fakes.gates),
        (OwnerSource, fakes.owner),
        (SessionSource, fakes.sessions),
        (JobSource, fakes.jobs),
    ):
        services.add(key, port)
    page = await team.now()
    assert (page.counts.needs_you, page.cycle.from_) == (0, "the last 7 days")


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
