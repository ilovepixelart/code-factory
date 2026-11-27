"""Queries over `check_runs`: the queue, the container turn and the heartbeat."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, any_, bindparam, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.checks.models import (
    CheckRun,
    Containment,
    RunState,
    Scope,
    Verdict,
)
from code_factory.checks.rules import CLAIM_HOLDS, claim_holds, next_turn
from code_factory.checks.tables import ONE_ACTIVE_WHERE, CheckRunRow
from code_factory.platform.db import lock_until_commit

TURN_LOCK = "checks:turn"  # the advisory lock that orders the container turn
LAPSE = CLAIM_HOLDS
_ACTIVE = (RunState.QUEUED.value, RunState.RUNNING.value)


def to_run(row: CheckRunRow) -> CheckRun:
    """A row as the value the service answers."""
    return CheckRun(
        id=row.id,
        repository=row.repository,
        subject=row.subject,
        scope=Scope(row.scope),
        commit=row.commit,
        tree_id=row.tree_id,
        state=RunState(row.state),
        contained=Containment(row.contained),
        owner=row.owner,
        requested_by=row.requested_by,
        queued_at=row.queued_at,
        started_at=row.started_at,
        beat_at=row.beat_at,
        finished_at=row.finished_at,
        exit_code=row.exit_code,
        verdict=None if row.verdict is None else Verdict(row.verdict),
        log_path=row.log_path,
        workspace=row.workspace,
    )


class RunStore:
    """Reads and writes of the runs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, values: dict[str, Any]) -> CheckRun | None:
        """A queued row, or None when the subject already has an active one."""
        # Publish each owner's inserts in id order so a later admission cannot strand an older
        # container row behind it.
        await lock_until_commit(self._session, f"checks:admission:{values['owner']}")
        statement = (
            insert(CheckRunRow)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["repository", "subject"],
                index_where=text(ONE_ACTIVE_WHERE),
            )
            .returning(CheckRunRow)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else to_run(row)

    async def get(self, check_id: int) -> CheckRun | None:
        """The run `check_id`."""
        row = await self._session.get(CheckRunRow, check_id)
        return None if row is None else to_run(row)

    async def latest(self, repository: str, subject: str) -> CheckRun | None:
        """The newest run of the subject."""
        statement = (
            select(CheckRunRow)
            .where(CheckRunRow.repository == repository, CheckRunRow.subject == subject)
            .order_by(CheckRunRow.id.desc())
            .limit(1)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else to_run(row)

    async def recent(self, limit: int, subject: str | None = None) -> list[CheckRun]:
        """The newest runs, optionally of one subject."""
        statement = select(CheckRunRow).order_by(CheckRunRow.id.desc()).limit(limit)
        if subject is not None:
            statement = statement.where(CheckRunRow.subject == subject)
        return [to_run(row) for row in (await self._session.execute(statement)).scalars()]

    async def active(self, repository: str | None = None) -> list[CheckRun]:
        """The queued and running runs, oldest first."""
        statement = select(CheckRunRow).where(CheckRunRow.state.in_(_ACTIVE))
        if repository is not None:
            statement = statement.where(CheckRunRow.repository == repository)
        rows = await self._session.execute(statement.order_by(CheckRunRow.id))
        return [to_run(row) for row in rows.scalars()]

    async def queued(self, owner: str, admitted: set[int], limit: int) -> list[int]:
        """The oldest queued ids the process has space to admit."""
        row = CheckRunRow
        rows = await self._session.scalars(
            select(row.id)
            .where(row.owner == owner, row.state == RunState.QUEUED.value, row.id.not_in(admitted))
            .order_by(row.id)
            .limit(limit)
        )
        return list(rows)

    async def adopt(self, check_id: int, owner: str, now: datetime) -> bool:
        """Make `owner` the process that runs a queued or running row and beat it.

        False when the row is gone or ended.
        """
        statement = (
            update(CheckRunRow)
            .where(CheckRunRow.id == check_id, CheckRunRow.state.in_(_ACTIVE))
            .values(owner=owner, beat_at=now)
            .returning(CheckRunRow.id)
        )
        return (await self._session.execute(statement)).first() is not None

    async def beat(
        self, check_ids: Sequence[int], owner: str, now: datetime, *, queued: bool = False
    ) -> bool:
        """Beat the active rows `owner` still holds, optionally including the durable queue."""
        ids = bindparam("check_ids", list(check_ids), type_=ARRAY(BigInteger))
        matching = CheckRunRow.id == any_(ids)
        if queued:
            matching = or_(matching, CheckRunRow.state == RunState.QUEUED.value)
        beaten = (
            update(CheckRunRow)
            .where(
                matching,
                CheckRunRow.owner == owner,
                CheckRunRow.state.in_(_ACTIVE),
            )
            .values(beat_at=now)
            .returning(CheckRunRow.id)
            .cte("beaten")
        )
        return bool(await self._session.scalar(select(select(beaten.c.id).exists())))

    async def start(self, check_id: int, now: datetime, values: dict[str, Any]) -> None:
        """A queued row begins to run, with what is known of it now (commit, tree id, log)."""
        await self._session.execute(
            update(CheckRunRow)
            .where(CheckRunRow.id == check_id, CheckRunRow.state == RunState.QUEUED.value)
            .values(state=RunState.RUNNING.value, started_at=now, beat_at=now, **values)
        )

    async def note(self, check_id: int, values: dict[str, Any]) -> None:
        """Set columns of a run that has not ended."""
        await self._session.execute(
            update(CheckRunRow)
            .where(CheckRunRow.id == check_id, CheckRunRow.state.in_(_ACTIVE))
            .values(**values)
        )

    async def finish(
        self, check_id: int, now: datetime, verdict: Verdict, values: dict[str, Any]
    ) -> None:
        """End a run with its verdict."""
        await self._session.execute(
            update(CheckRunRow)
            .where(CheckRunRow.id == check_id, CheckRunRow.state.in_(_ACTIVE))
            .values(
                state=RunState.FINISHED.value,
                verdict=verdict.value,
                finished_at=now,
                beat_at=now,
                **values,
            )
        )

    async def lose(self, check_id: int, now: datetime) -> bool:
        """End a run that has no verdict because its process went away."""
        statement = (
            update(CheckRunRow)
            .where(CheckRunRow.id == check_id, CheckRunRow.state.in_(_ACTIVE))
            .values(state=RunState.LOST.value, finished_at=now)
            .returning(CheckRunRow.id)
        )
        return (await self._session.execute(statement)).first() is not None

    async def reconcile(self, now: datetime) -> list[int]:
        """Mark runs unbeaten for 60 s lost; the ids."""
        statement = (
            update(CheckRunRow)
            .where(CheckRunRow.state.in_(_ACTIVE), CheckRunRow.beat_at < now - LAPSE)
            .values(state=RunState.LOST.value, finished_at=now)
            .returning(CheckRunRow.id)
        )
        return sorted((await self._session.execute(statement)).scalars())

    async def take_turn(self, check_id: int, slots: int, now: datetime) -> bool:
        """Start the container run `check_id` when it is next and a slot is free.

        Decided under an advisory lock held to the end of the transaction, so two processes never
        take the same slot. A row unbeaten for 60 s counts as gone.
        """
        await lock_until_commit(self._session, TURN_LOCK)
        rows = (
            await self._session.execute(
                select(CheckRunRow.id, CheckRunRow.state, CheckRunRow.beat_at).where(
                    CheckRunRow.contained == Containment.CONTAINER.value,
                    CheckRunRow.state.in_(_ACTIVE),
                )
            )
        ).all()
        live = [(i, state) for i, state, beat in rows if claim_holds(beat, now)]
        if (check_id, RunState.RUNNING.value) in live:
            return True  # a retry after a kill: the row holds its slot already
        queued = [i for i, state in live if state == RunState.QUEUED.value]
        running = sum(1 for _, state in live if state == RunState.RUNNING.value)
        if next_turn(queued, running, slots) != check_id:
            return False
        await self.start(check_id, now, {})
        return True

    async def prunable(self, before: datetime) -> int:
        """How many finished and lost runs ended before `before`."""
        statement = select(func.count()).where(
            CheckRunRow.state.in_([RunState.FINISHED.value, RunState.LOST.value]),
            or_(CheckRunRow.finished_at < before, CheckRunRow.finished_at.is_(None)),
        )
        return (await self._session.execute(statement)).scalar_one()

    async def prune(self, before: datetime) -> int:
        """Delete finished and lost runs that ended before `before`."""
        statement = delete(CheckRunRow).where(
            CheckRunRow.state.in_([RunState.FINISHED.value, RunState.LOST.value]),
            or_(CheckRunRow.finished_at < before, CheckRunRow.finished_at.is_(None)),
        )
        return len((await self._session.execute(statement.returning(CheckRunRow.id))).all())
