"""The metrics service: the module's public API. Each method is one use case."""

import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import datetime

from code_factory.metrics.adapters import GitReader
from code_factory.metrics.models import (
    FlowPage,
    Forecast,
    Merge,
    RefreshResult,
    StageMove,
    StepTime,
    TimesReport,
    TrackedRepo,
    Yield,
)
from code_factory.metrics.ports import MetricsPorts
from code_factory.metrics.repository import MetricsRepository
from code_factory.metrics.rules.merges import parse_merges
from code_factory.metrics.service import reports
from code_factory.metrics.service.deps import Deps, utc_now
from code_factory.metrics.service.flow import WebAddresses, flow_page
from code_factory.metrics.service.refresh import refresh_repository
from code_factory.platform.db import UnitOfWork

logger = logging.getLogger(__name__)
LOOP_INTERVAL_S = 30.0
PASS_TIMEOUT_S = 120.0


class MetricsService:
    """How work moves: the Flow page, gate step times and the reports built on the ledger."""

    def __init__(  # noqa: PLR0913  # the collaborators, with their limits
        self,
        uow: UnitOfWork,
        ports: MetricsPorts,
        git: GitReader,
        now: Callable[[], datetime] = utc_now,
        *,
        pass_timeout_s: float = PASS_TIMEOUT_S,
        loop_interval_s: float = LOOP_INTERVAL_S,
    ) -> None:
        self._deps = Deps(uow, ports, git, now)
        self._web = WebAddresses()
        self._pass_timeout_s = pass_timeout_s
        self._loop_interval_s = loop_interval_s

    async def flow(self, range_name: str | None = None) -> FlowPage:
        """The Flow page for `24h`, `7d` or `30d`; any other text, or none, reads as `7d`."""
        return await flow_page(self._deps, self._web, range_name)

    async def merged_at(self, tickets: Sequence[str]) -> dict[str, float]:
        """When each ticket's work landed on its default branch, as the Flow page counts it."""
        async with self._deps.uow() as session:
            found = await MetricsRepository(session).first_merged(tickets)
        return {ticket: at.timestamp() for ticket, at in found.items()}

    async def refresh(self, repository: str | None = None) -> list[RefreshResult]:
        """Bring the ledger up to date from git, for one repository or every tracked one.

        A repository whose pass fails is logged and skipped when none is named; a named one raises
        its error. `NotFoundError` for a name that is not tracked.
        """
        repos = await self._deps.repositories(repository)
        results: list[RefreshResult] = []
        for repo in repos:
            if repository is not None:
                results.append(await self._pass(repo))
                continue
            try:
                results.append(await self._pass(repo))
            except Exception:
                logger.exception("metrics refresh of %s failed", repo.name)
        return results

    async def _pass(self, repo: TrackedRepo) -> RefreshResult:
        async with asyncio.timeout(self._pass_timeout_s):
            return await refresh_repository(self._deps, repo)

    async def run_refresh_loop(self) -> None:
        """Refresh every repository now and every 30 s; ends only when its task is cancelled."""
        while True:
            try:
                await self.refresh()
            except Exception:
                logger.exception("metrics refresh pass failed")
            await asyncio.sleep(self._loop_interval_s)

    async def step_times(self, last: int | None = None) -> list[StepTime]:
        """Each gate step over the newest `last` runs (all when None); `BadRequestError` below 1."""
        return await reports.step_times(self._deps, last)

    async def times_report(self, last: int = 50, repository: str | None = None) -> TimesReport:
        """Step times, minutes per column and reverts since the oldest of the last `last` runs."""
        return await reports.times_report(self._deps, last, repository)

    async def throughput(self, repository: str | None = None) -> list[int]:
        """Tickets first reaching review in each of the last eight UTC weeks, oldest first."""
        return await reports.weekly_throughput(self._deps, repository)

    async def forecast(
        self, open_tickets: int | None = None, repository: str | None = None
    ) -> Forecast:
        """In how many days the open tickets are done (default: those not yet in review)."""
        return await reports.forecast_open(self._deps, open_tickets, repository)

    async def factory(self, repository: str | None = None) -> list[Yield]:
        """The yield of each agent and model on merged work."""
        return await reports.factory_yields(self._deps, repository)

    @staticmethod
    def reached_done(moves: Sequence[StageMove]) -> datetime | None:
        """When a ticket first reached review or later, from its moves (oldest first)."""
        return reports.reached_done(moves)

    @staticmethod
    def merges_in_log(log: str, since: float = 0.0) -> list[Merge]:
        """The pull requests a `git log --format=%H%x1f%P%x1f%ct%x1f%B%x1e` merged since `since`."""
        return parse_merges(log, since)
