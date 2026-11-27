"""Reading runs: one run, a ticket's runs, the views the board, the team and the MCP tools show."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from code_factory.agents.service import StartKit
from code_factory.platform.errors import CodeFactoryError, NotFoundError
from code_factory.runs.adapters import files
from code_factory.runs.adapters.processes import Target
from code_factory.runs.models import (
    ActiveRun,
    BudgetScope,
    DayUsage,
    Run,
    RunCost,
    RunView,
)
from code_factory.runs.ports import Given, Settings, TicketFacts
from code_factory.runs.repository import RunRepository
from code_factory.runs.rules import budget as budget_rules
from code_factory.runs.rules.budget import Spent, period
from code_factory.runs.rules.records import state_of
from code_factory.runs.rules.usage import usage_csv, usage_rows
from code_factory.runs.service.base import ServiceBase

LOG_SERVED = 1024 * 1024
TICKET_PREFIX = "CF-"
NEVER = datetime.min.replace(tzinfo=UTC)


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    """The UTC month `now` falls in, as a half-open interval."""
    start = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    following = (start + timedelta(days=32)).replace(day=1)
    return start, following


def view_of(run: Run) -> RunView:
    """What a board card and `list_runs` show of a run."""
    return RunView(
        id=run.id,
        ticket_id=run.ticket_key,
        stage=run.stage,
        agent=run.agent,
        model=run.model,
        state=state_of(run),
        started_at=run.started_at,
        ended_at=run.ended_at,
        exit_code=run.exit_code,
        halted=run.halted,
        limited_until=run.limited_until,
        tokens=run.tokens,
        cost=run.cost,
        cost_estimated=run.cost_estimated,
        commits=run.commits,
        uncommitted=run.uncommitted,
    )


def ticket_number(ticket_id: str) -> int | None:
    """The number of a ticket id `CF-<n>`, `None` for anything else."""
    digits = ticket_id.removeprefix(TICKET_PREFIX)
    return (
        int(digits)
        if ticket_id.startswith(TICKET_PREFIX) and digits.isascii() and digits.isdigit()
        else None
    )


class Reading(ServiceBase):
    """What the service answers about recorded runs."""

    async def get(self, run_id: str) -> Run:
        """The run; `NotFoundError("no such run")` for an unknown id."""
        async with self._uow() as session:
            run = await RunRepository(session).get(run_id)
        if run is None:
            msg = "no such run"
            raise NotFoundError(msg)
        return run

    async def list_for_ticket(
        self, ticket_id: str, state: str | None = None, limit: int | None = None
    ) -> list[RunView]:
        """The ticket's runs, newest first, optionally of one state and at most `limit`."""
        number = ticket_number(ticket_id)
        if number is None:
            msg = f"no such ticket {ticket_id}"
            raise NotFoundError(msg)
        async with self._uow() as session:
            runs = await RunRepository(session).for_ticket(number)
        views = [view_of(run) for run in runs if state is None or state_of(run) == state]
        return views if limit is None else views[:limit]

    async def card_runs(self, ticket_ids: Sequence[str]) -> dict[str, list[RunView]]:
        """Each ticket's runs, newest first; a ticket with none has an empty list."""
        numbers = {n: i for i in ticket_ids if (n := ticket_number(i)) is not None}
        async with self._uow() as session:
            runs = await RunRepository(session).for_tickets(list(numbers))
        found: dict[str, list[RunView]] = {i: [] for i in ticket_ids}
        for run in runs:
            if run.ticket_id in numbers:
                found[numbers[run.ticket_id]].append(view_of(run))
        return found

    async def runs_on_tickets(self, ticket_ids: Sequence[str]) -> list[Run]:
        """Every run for the named tickets in one query."""
        numbers = [n for ticket in ticket_ids if (n := ticket_number(ticket)) is not None]
        if not numbers:
            return []
        async with self._uow() as session:
            return await RunRepository(session).for_tickets(numbers)

    async def runs_on_ticket(self, ticket_id: str) -> list[Run]:
        """Every run of the ticket, newest first."""
        number = ticket_number(ticket_id)
        if number is None:
            return []
        async with self._uow() as session:
            return await RunRepository(session).for_ticket(number)

    async def latest_runs(self, agent_names: Sequence[str]) -> list[Run]:
        """The latest run by start of each named agent."""
        async with self._uow() as session:
            return await RunRepository(session).latest_by_agent(agent_names)

    async def runs_since(self, moment: datetime) -> list[Run]:
        """Every run started at or after `moment`."""
        async with self._uow() as session:
            return await RunRepository(session).since(moment)

    async def runs_by_ids(self, ids: Sequence[str]) -> list[Run]:
        """The recorded runs among `ids`; an id with no record is left out."""
        async with self._uow() as session:
            return await RunRepository(session).by_ids(ids)

    async def active_runs(self) -> list[ActiveRun]:
        """Every run with no exit and whether its process lives; one not started yet is alive."""
        async with self._uow() as session:
            active = await RunRepository(session).active()
        found: list[ActiveRun] = []
        for run in active:
            alive = True
            if run.pid is not None:
                alive = await self._registry.alive(
                    Target(run.pid, run.pid_started_at, self.exit_file_of(run))
                )
            found.append(ActiveRun(run=run, alive=alive))
        return found

    async def build_starts(self, repository: str, since: datetime, until: datetime) -> list[Run]:
        """The build runs the repository started in `[since, until)`, oldest first."""
        async with self._uow() as session:
            runs = await RunRepository(session).between(repository, since, until)
        return [run for run in runs if run.stage == "build"]

    async def cost_between(self, repository: str, start: datetime, end: datetime) -> float:
        """What the repository's runs started in `[start, end)` cost."""
        async with self._uow() as session:
            return await RunRepository(session).cost_between(repository, start, end)

    async def usage(self, since: datetime | None = None) -> list[DayUsage]:
        """Usage per UTC day, agent and model of the runs started at or after `since`."""
        async with self._uow() as session:
            runs = await RunRepository(session).since(since or NEVER)
        return usage_rows(runs)

    async def usage_csv(self, since: datetime | None = None) -> str:
        """`usage` as CSV."""
        return usage_csv(await self.usage(since))

    async def log(self, run_id: str) -> str:
        """The last mebibyte of the run's log from a line's start; empty before it is written.

        `NotFoundError` for an id that is not letters and digits or names no run.
        """
        msg = f"no run {run_id}"
        if not (run_id.isascii() and run_id.isalnum()):
            raise NotFoundError(msg)
        async with self._uow() as session:
            run = await RunRepository(session).get(run_id)
        if run is None:
            raise NotFoundError(msg)
        return await files.read_tail(Path(run.log), LOG_SERVED) or ""

    async def month_budget(self, repository: str, now: datetime) -> BudgetScope | None:
        """The repository's monthly cap and what its runs spent this month; `None` without a cap."""
        settings = await self._ports.config.settings(repository)
        return await self._month_scope(repository, settings, now)

    async def _month_scope(
        self, repository: str, settings: Settings, now: datetime
    ) -> BudgetScope | None:
        cap = StartKit.monthly_budget(settings.monthly_budget_usd)
        if cap is None:
            return None
        start, following = month_bounds(now)
        async with self._uow() as session:
            spent = await RunRepository(session).cost_between(repository, start, following)
        return BudgetScope(name="month", budget=cap, spent=spent, month=period("month", now))

    async def scopes(
        self, facts: TicketFacts, settings: Settings, now: datetime | None = None
    ) -> list[BudgetScope]:
        """The budgets a run of the ticket is checked against: its own, then the month's."""
        found: list[BudgetScope] = []
        if (cap := StartKit.ticket_budget(facts.budget, settings.budget_usd)) is not None:
            async with self._uow() as session:
                spent = await RunRepository(session).ticket_cost(facts.number)
            found.append(BudgetScope(name="ticket", budget=cap, spent=spent))
        if (
            month := await self._month_scope(facts.repository, settings, now or self._clock())
        ) is not None:
            found.append(month)
        return found

    async def _given(self, run: Run) -> Given | None:
        try:
            return await self._ports.agents.given(run.agent, run.stage)
        except CodeFactoryError:
            return None  # the agent was removed: its price is unknown

    async def _priced(self, run: Run) -> bool:
        given = await self._given(run)
        return (
            given is not None and given.input_price is not None and given.output_price is not None
        )

    async def review_unpaid(self, ticket_id: str, now: datetime) -> Spent | None:
        """Why the board does not pay for a review of the ticket; `None` when it pays.

        Its budget or the month's is spent, or a priced run recorded no cost so the spend is
        unknown.
        """
        facts = await self._ports.tickets.facts(ticket_id)
        settings = await self._ports.config.settings(facts.repository)
        scopes = await self.scopes(facts, settings, now)
        async with self._uow() as session:
            repo = RunRepository(session)
            runs = await repo.for_ticket(facts.number)
            start, following = month_bounds(now)
            runs += await repo.between(facts.repository, start, following)
        known = {r.id: r for r in runs}
        costs = [
            RunCost(
                id=r.id, priced=await self._priced(r), cost=r.cost, ended=r.exit_code is not None
            )
            for r in known.values()
        ]
        return budget_rules.review_unpaid(scopes, costs)
