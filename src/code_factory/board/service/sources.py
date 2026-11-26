"""The services and ports the board reads from."""

from dataclasses import dataclass

from code_factory.board.ports import (
    CardChecks,
    CardDelivery,
    CardQueue,
    CardRuns,
    ColumnLimits,
)
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.sessions.service import SessionService
from code_factory.settings.service import SettingsService
from code_factory.stages.service import StageService
from code_factory.talk.service import TalkService
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)


@dataclass(frozen=True)
class BoardSources:
    """Everything the board reads: other modules' services, and ports over the ones it renames."""

    tickets: TicketService
    documents: DocumentService
    activity: ActivityService
    reviews: ReviewService
    talk: TalkService
    repositories: RepositoryService
    settings: SettingsService
    stages: StageService
    sessions: SessionService
    releases: ReleaseService
    queue: CardQueue
    runs: CardRuns
    checks: CardChecks
    delivery: CardDelivery
    limits: ColumnLimits
