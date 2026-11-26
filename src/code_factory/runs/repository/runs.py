"""Queries over the `runs` table."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.errors import ConflictError
from code_factory.runs.models import Run
from code_factory.runs.tables import RunRow

_UNIQUE_VIOLATION = "23505"
_ACTIVE = RunRow.exit_code.is_(None)


@dataclass(frozen=True)
class RunEnd:
    """What a run's end records: its exit and what its log and worktree said."""

    exit_code: int
    ended_at: datetime
    cost: float | None = None
    cost_estimated: bool = False
    tokens: int | None = None
    cache_read: int | None = None
    turns: int | None = None
    model: str | None = None
    uncommitted: bool = False
    commits: list[str] | None = None
    halted: str | None = None
    limited_until: datetime | None = None
    looping: bool | None = None
    extra: dict[str, object] = field(default_factory=dict)


def _run(row: RunRow) -> Run:
    return Run.model_validate(row, from_attributes=True)


def _end_values(end: RunEnd) -> dict[str, object]:
    values: dict[str, object] = {
        "exit_code": end.exit_code,
        "ended_at": end.ended_at,
        "cost": None if end.cost is None else Decimal(str(end.cost)),
        "cost_estimated": end.cost_estimated,
        "tokens": end.tokens,
        "cache_read": end.cache_read,
        "turns": end.turns,
        "uncommitted": end.uncommitted,
        "commits": end.commits,
        "limited_until": end.limited_until,
    }
    optional = {"model": end.model, "halted": end.halted, "looping": end.looping}
    values.update({name: value for name, value in optional.items() if value is not None})
    return values | end.extra


def _spent(total: Decimal | None) -> float:
    return float(total or 0)


class RunRepository:
    """Runs: one row each, ended by a compare-and-set so a side effect of an end happens once."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, run: Run) -> Run:
        """Record a run.

        `ConflictError` when the ticket and attempt already have an active run, or the repository
        an active coordinator: the database's partial unique indexes decide, not a prior read.
        """
        row = RunRow(**run.model_dump())
        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", "") != _UNIQUE_VIOLATION:
                raise
            if run.stage == "coordinate":
                msg = f"a coordinator is already running for {run.repository}"
            else:
                msg = "an agent is already running on this ticket"
            raise ConflictError(msg) from error
        return _run(row)

    async def get(self, run_id: str) -> Run | None:
        """The run, or `None`."""
        row = await self._session.get(RunRow, run_id)
        return None if row is None else _run(row)

    async def set_pid(self, run_id: str, pid: int, started_at: datetime | None) -> bool:
        """Record the process of a run that has not ended; `False` when it has.

        `started_at` is `None` when `ps` could not read it: the pid is still the held child's.
        """
        done = await self._session.scalar(
            update(RunRow)
            .where(RunRow.id == run_id, _ACTIVE)
            .values(pid=pid, pid_started_at=started_at)
            .returning(RunRow.id)
        )
        return done is not None

    async def change(self, run_id: str, **values: object) -> bool:
        """Set columns of a run (its head, its context); `False` for an unknown run."""
        done = await self._session.scalar(
            update(RunRow).where(RunRow.id == run_id).values(**values).returning(RunRow.id)
        )
        return done is not None

    async def end(self, run_id: str, end: RunEnd) -> Run | None:
        """End the run when it has no exit yet: the winner gets the run, any other `None`."""
        row = (
            await self._session.execute(
                update(RunRow)
                .where(RunRow.id == run_id, _ACTIVE)
                .values(**_end_values(end))
                .returning(RunRow)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        return None if row is None else _run(row)

    async def settle(self, run_id: str, at: datetime) -> None:
        """Record that the side effects of the run's end ran."""
        await self._session.execute(
            update(RunRow)
            .where(RunRow.id == run_id, RunRow.settled_at.is_(None))
            .values(settled_at=at)
        )

    async def active(self) -> list[Run]:
        """Every run with no exit, oldest first."""
        return await self._many(select(RunRow).where(_ACTIVE).order_by(RunRow.started_at))

    async def unsettled(self) -> list[Run]:
        """Ended runs whose end's side effects are not recorded as done."""
        return await self._many(
            select(RunRow)
            .where(RunRow.exit_code.is_not(None), RunRow.settled_at.is_(None))
            .order_by(RunRow.ended_at)
        )

    async def unspawned_before(self, moment: datetime) -> list[Run]:
        """Active runs started before `moment` that never recorded a process."""
        return await self._many(
            select(RunRow).where(_ACTIVE, RunRow.pid.is_(None), RunRow.started_at < moment)
        )

    async def for_ticket(self, number: int, *, limit: int | None = None) -> list[Run]:
        """The ticket's runs, newest first."""
        query = select(RunRow).where(RunRow.ticket_id == number).order_by(RunRow.started_at.desc())
        return await self._many(query.limit(limit) if limit is not None else query)

    async def for_tickets(self, numbers: Sequence[int]) -> list[Run]:
        """The runs of these tickets, newest first."""
        return await self._many(
            select(RunRow).where(RunRow.ticket_id.in_(numbers)).order_by(RunRow.started_at.desc())
        )

    async def by_ids(self, ids: Sequence[str]) -> list[Run]:
        """The recorded runs among `ids`."""
        return await self._many(select(RunRow).where(RunRow.id.in_(ids)))

    async def since(self, moment: datetime) -> list[Run]:
        """Runs started at or after `moment`, oldest first."""
        return await self._many(
            select(RunRow).where(RunRow.started_at >= moment).order_by(RunRow.started_at)
        )

    async def between(self, repository: str, start: datetime, end: datetime) -> list[Run]:
        """The repository's runs started in the half-open interval, oldest first."""
        return await self._many(
            select(RunRow)
            .where(
                RunRow.repository == repository,
                RunRow.started_at >= start,
                RunRow.started_at < end,
            )
            .order_by(RunRow.started_at)
        )

    async def latest_by_agent(self, names: Sequence[str]) -> list[Run]:
        """The latest run by start of each named agent."""
        latest = (
            select(RunRow)
            .where(RunRow.agent.in_(names))
            .ext(distinct_on(RunRow.agent))
            .order_by(RunRow.agent, RunRow.started_at.desc())
        )
        return await self._many(latest)

    async def cost_between(self, repository: str, start: datetime, end: datetime) -> float:
        """What the repository's runs started in `[start, end)` cost; no cost counts as nothing."""
        total = await self._session.scalar(
            select(func.sum(RunRow.cost)).where(
                RunRow.repository == repository,
                RunRow.started_at >= start,
                RunRow.started_at < end,
            )
        )
        return _spent(total)

    async def ticket_cost(self, number: int) -> float:
        """What every run of the ticket cost."""
        total = await self._session.scalar(
            select(func.sum(RunRow.cost)).where(RunRow.ticket_id == number)
        )
        return _spent(total)

    async def _many(self, query: Select[Any]) -> list[Run]:
        rows = (await self._session.execute(query)).scalars().all()
        return [_run(row) for row in rows]
