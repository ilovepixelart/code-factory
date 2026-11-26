"""The `stages` module as the platform sees it.

List it after tickets, git, releases, repositories and settings: it reads their services.
The observer (`stage-observer`) starts with the HTTP app; `CODE_FACTORY_STAGE_OBSERVE_SECONDS`
sets its period.
"""

import math
import os

from code_factory.git.service import GitService
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.errors import SettingsError
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService
from code_factory.stages import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.stages.adapters import GitServiceFacts
from code_factory.stages.cli import stage_command
from code_factory.stages.service import Ports, StageService
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)

OBSERVE_VARIABLE = "CODE_FACTORY_STAGE_OBSERVE_SECONDS"
DEFAULT_OBSERVE_S = 30.0
MINIMUM_OBSERVE_S = 5.0


def observe_period(environment: dict[str, str] | None = None) -> float:
    """The observer's period in seconds: the variable, default 30, never under 5."""
    given = (environment if environment is not None else os.environ).get(OBSERVE_VARIABLE)
    if given is None or not given.strip():
        return DEFAULT_OBSERVE_S
    try:
        seconds = float(given)
    except ValueError:
        seconds = math.nan
    if not math.isfinite(seconds):
        msg = f"{OBSERVE_VARIABLE} is {given!r}: write the seconds between observations, as 30"
        raise SettingsError(msg) from None
    return max(seconds, MINIMUM_OBSERVE_S)


def _provide(services: Services, resources: Resources) -> None:
    ports = Ports(
        tickets=services.get(TicketService),
        reviews=services.get(ReviewService),
        activity=services.get(ActivityService),
        documents=services.get(DocumentService),
        releases=services.get(ReleaseService),
        repositories=services.get(RepositoryService),
        settings=services.get(SettingsService),
        facts=GitServiceFacts(services.get(GitService)),
    )
    services.add(StageService, StageService(resources.uow, ports))


def _background(services: Services, tasks: BackgroundTasks) -> None:
    stages = services.get(StageService)
    period = observe_period()
    tasks.start("stage-observer", lambda: stages.run_observer(period))


module = Module(name="stages", provide=_provide, commands=(stage_command,), background=_background)
