"""The `team` module as the platform sees it.

List it before the modules that register ports for it (agents, runs, tickets, inbox, sessions,
checks): they import `team.service`, and the team imports none of them. Its service resolves its
ports lazily, at the first call, so the order in `app.MODULES` does not matter for them.
"""

from typing import cast

from code_factory.platform.background import BackgroundTasks
from code_factory.platform.errors import UnavailableError
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.team import tables  # noqa: F401  # puts the team tables on Base.metadata
from code_factory.team.adapters import GitFacts
from code_factory.team.cli import team_command
from code_factory.team.routes import router
from code_factory.team.service import (
    AgentSource,
    GateSource,
    JobSource,
    OwnerSource,
    RunSource,
    SessionSource,
    TeamPorts,
    TeamService,
    TicketSource,
)


class _Registered[T]:
    """A port that is looked up in the registry when it is used, not when the team is built.

    A call that needs only some ports then works while the others are not registered; one that
    needs a missing port says so in one sentence.
    """

    def __init__(self, services: Services, key: type[T]) -> None:
        self._services = services
        self._key = key

    def __getattr__(self, name: str) -> object:
        try:
            port = self._services.get(self._key)
        except LookupError as missing:
            raise UnavailableError(f"the team cannot reach its sources: {missing}") from missing
        return getattr(port, name)


def _provide(services: Services, resources: Resources) -> None:
    def registered[T](key: type[T]) -> T:
        return cast("T", _Registered(services, key))

    ports = TeamPorts(
        agents=registered(AgentSource),
        runs=registered(RunSource),
        tickets=registered(TicketSource),
        gates=registered(GateSource),
        owner=registered(OwnerSource),
        sessions=registered(SessionSource),
        jobs=registered(JobSource),
    )
    services.add(TeamService, TeamService(resources.uow, lambda: ports, git=GitFacts()))


def _background(services: Services, tasks: BackgroundTasks) -> None:
    team = services.get(TeamService)
    tasks.start("team-keeper", team.run_keeper)


module = Module(
    name="team",
    provide=_provide,
    router=router,
    commands=(team_command,),
    background=_background,
)
