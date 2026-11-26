"""The module's registration: its service resolves its ports from the registry at call time."""

import pytest

from code_factory.app import MODULES, build_resources, build_services
from code_factory.platform.config import Settings
from code_factory.platform.errors import UnavailableError
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
