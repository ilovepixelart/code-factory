"""The `sample` module as the platform sees it."""

from code_factory.agents.service import AgentService
from code_factory.auth.service import AuthService
from code_factory.board.service import BoardService
from code_factory.checks.service import CheckService
from code_factory.delivery.service import DeliveryService
from code_factory.evals.service import JudgeService
from code_factory.memory.service import MemoryService
from code_factory.metrics.service import MetricsService
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.runs.service import RunService
from code_factory.sample.cli import commands
from code_factory.sample.models import OWNER_ENTROPY
from code_factory.sample.service import SampleService
from code_factory.sample.service.demo import DemoDeps
from code_factory.screens.service import ScreensService
from code_factory.sessions.service import SessionService
from code_factory.stages.service import StageService
from code_factory.talk.service import TalkService
from code_factory.team.service import TeamService
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)


def _fixed_entropy(count: int) -> bytes:
    return OWNER_ENTROPY[:count]


def _demo(services: Services, resources: Resources) -> DemoDeps:
    return DemoDeps(
        tickets=services.get(TicketService),
        tickets_at=lambda at: TicketService(resources.uow, clock=lambda: at),
        board=services.get(BoardService),
        writes=services.get(TicketWriteService),
        documents=services.get(DocumentService),
        activities=services.get(ActivityService),
        reviews=services.get(ReviewService),
        memory=services.get(MemoryService),
        talk=services.get(TalkService),
        talk_at=lambda at: TalkService(resources.uow, clock=lambda: at),
        agents=services.get(AgentService),
        team=services.get(TeamService),
        repositories=services.get(RepositoryService),
        releases=services.get(ReleaseService),
        stages=services.get(StageService),
        checks=services.get(CheckService),
        metrics=services.get(MetricsService),
        sessions=services.get(SessionService),
        screens=services.get(ScreensService),
        runs=services.get(RunService),
        judge=services.get(JudgeService),
        delivery=services.get(DeliveryService),
    )


def _provide(services: Services, resources: Resources) -> None:
    services.add(
        SampleService,
        SampleService(
            AuthService(resources.uow, entropy=_fixed_entropy),
            services.get(TicketService),
            services.get(DocumentService),
            services.get(MemoryService),
            (_demo(services, resources), resources.settings.state_dir),
        ),
    )


module = Module(name="sample", provide=_provide, commands=commands)
