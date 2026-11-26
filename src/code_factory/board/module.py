"""The `board` module as the platform sees it.

List it after the modules it reads (tickets, talk, releases, stages, sessions, team, agents, runs,
checks, delivery, ticket_writes).
"""

from code_factory.board import tables  # noqa: F401  # puts board_views on Base.metadata
from code_factory.board.adapters import (
    NoJobs,
    TeamOwner,
    TeamReads,
    TeamTickets,
)
from code_factory.board.routes import router
from code_factory.board.service import (
    BoardService,
    BoardSources,
    CardChecks,
    CardDelivery,
    CardQueue,
    CardRuns,
    ColumnLimits,
    MergeLedger,
)
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.sessions.service import SessionService
from code_factory.settings.service import SettingsService
from code_factory.stages.service import StageService
from code_factory.talk.service import TalkService
from code_factory.team.service import (
    JobSource,
    OwnerSource,
    TicketSource,
)
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)


def board_sources(services: Services) -> BoardSources:
    """The services the board reads, and the ports the runs, checks, delivery and limits answer."""
    return BoardSources(
        tickets=services.get(TicketService),
        documents=services.get(DocumentService),
        activity=services.get(ActivityService),
        reviews=services.get(ReviewService),
        talk=services.get(TalkService),
        repositories=services.get(RepositoryService),
        settings=services.get(SettingsService),
        stages=services.get(StageService),
        sessions=services.get(SessionService),
        releases=services.get(ReleaseService),
        queue=services.get(CardQueue),
        runs=services.get(CardRuns),
        checks=services.get(CardChecks),
        delivery=services.get(CardDelivery),
        limits=services.get(ColumnLimits),
    )


def _provide(services: Services, resources: Resources) -> None:
    sources = board_sources(services)
    services.add(BoardService, BoardService(sources, resources.uow))
    # The agents, runs, checks and sessions modules register the team's other ports in their own
    # provide.
    services.add(
        TicketSource,
        TeamTickets(
            sources.tickets,
            sources.repositories,
            sources.activity,
            TeamReads(
                events=sources.delivery.events,
                merges=services.get(MergeLedger).merged_at,
                pulls=sources.delivery.pulls,
                checks=sources.checks.latest_checks,
            ),
        ),
    )
    services.add(OwnerSource, TeamOwner(sources.tickets, sources.talk))
    services.add(JobSource, NoJobs())


module = Module(name="board", provide=_provide, router=router)
