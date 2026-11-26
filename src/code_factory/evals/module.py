"""The `evals` module as the platform sees it."""

from datetime import UTC, datetime

from code_factory.evals import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.evals.cli import eval_command
from code_factory.evals.routes import router
from code_factory.evals.service import EvalService, JudgeService
from code_factory.evals.service.neighbours import PlacesAdapter, TicketsAdapter
from code_factory.factory.models import ScorerCard, ScorerCards
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services


def _at(moment: float) -> datetime:
    return datetime.fromtimestamp(moment, UTC)


class ScorerAnswers:
    """The scorers' answers in a window."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def cards(self, since: float, until: float) -> ScorerCards:
        """One card per configured scorer."""
        found = await self._services.get(JudgeService).scorer_counts(_at(since), _at(until))
        return ScorerCards(
            available=True,
            cards=[
                ScorerCard(
                    repository=repository,
                    name=scorer.name,
                    question=scorer.question,
                    yes=c.yes,
                    no=c.no,
                    unclear=c.unclear,
                    average_score=None,
                    window_since=since,
                    window_until=until,
                )
                for repository, scorer, c in found
            ],
        )


def _provide(services: Services, resources: Resources) -> None:
    services.add(EvalService, EvalService(resources.uow))
    services.add(
        JudgeService,
        JudgeService(resources.uow, PlacesAdapter(services), TicketsAdapter(services)),
    )


module = Module(name="evals", provide=_provide, commands=(eval_command,), router=router)
