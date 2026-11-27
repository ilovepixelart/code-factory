"""Queries over the evals tables. Every method runs in the session it is given."""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select, union_all, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.evals.models import (
    Answer,
    AnswerRow,
    EvalRecord,
    Kind,
    Role,
    Setup,
    StartedBy,
    TaskRun,
)
from code_factory.evals.tables import EvalRecordRow, EvalTaskRunRow, JudgeDayRow, JudgementRow
from code_factory.platform.errors import ConflictError

STALE_CLAIM = timedelta(hours=2)


def _record(row: EvalRecordRow, runs: list[EvalTaskRunRow]) -> EvalRecord:
    return EvalRecord(
        id=row.id,
        repository=row.repository,
        set_name=row.set_name,
        kind=Kind(row.kind),
        recorded_at=row.recorded_at,
        setup=Setup(
            stage=row.stage,
            runtime=row.runtime,
            model=row.model,
            instructions=row.instructions,
            memory=row.memory,
            lesson=row.lesson,
            agent=row.agent,
            connection=row.connection,
        ),
        runs=row.runs,
        pass_at_1=row.pass_at_1,
        pass_k=row.pass_k,
        pass_at_k=row.pass_at_k,
        caught=row.caught,
        false_findings=row.false_findings,
        failed=row.failed,
        cost=row.cost,
        tokens=row.tokens,
        receipt=row.receipt,
        task_runs=tuple(
            TaskRun(
                task_id=r.task_id,
                run_no=r.run_no,
                role=Role(r.role),
                passed=r.passed,
                blocking=r.blocking,
            )
            for r in runs
        ),
    )


class EvalRepository:
    """Records, judgements and judge-day claims."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_record(self, record: EvalRecord) -> int:
        """Store a suite run with its tasks, or return the id of the same receipt."""
        values = record.model_dump(exclude={"id", "setup", "task_runs"}) | record.setup.model_dump()
        table = EvalRecordRow
        insert = pg_insert(table).values(**values)
        if record.receipt is not None:
            insert = insert.on_conflict_do_nothing(
                index_elements=[table.repository, table.receipt],
                index_where=table.receipt.is_not(None),
            )
        record_id = await self._session.scalar(insert.returning(table.id))
        if record_id is None:
            return await self._same_receipt(record)
        for run in record.task_runs:
            self._session.add(EvalTaskRunRow(record_id=record_id, **run.model_dump()))
        await self._session.flush()
        return record_id

    async def _same_receipt(self, record: EvalRecord) -> int:
        table = EvalRecordRow
        stored = (
            await self._session.scalars(
                select(table).where(
                    table.repository == record.repository, table.receipt == record.receipt
                )
            )
        ).one()
        runs = list(
            await self._session.scalars(
                select(EvalTaskRunRow)
                .where(EvalTaskRunRow.record_id == stored.id)
                .order_by(EvalTaskRunRow.task_id, EvalTaskRunRow.run_no)
            )
        )
        tasks = tuple(sorted(record.task_runs, key=lambda result: (result.task_id, result.run_no)))
        if _record(stored, runs) != record.model_copy(update={"id": stored.id, "task_runs": tasks}):
            msg = f"evaluation receipt {record.receipt!r} already identifies a different result"
            raise ConflictError(msg)
        return stored.id

    async def measurement_spend(self, since: datetime, until: datetime) -> float | None:
        """Sum measured evaluations and judgements in the window, unknown without a known cost."""
        suite, judge = EvalRecordRow, JudgementRow
        rows = union_all(
            select(suite.cost).where(
                suite.recorded_at >= since,
                suite.recorded_at < until,
                suite.cost.is_not(None),
                suite.cost < float("inf"),
            ),
            select(judge.cost).where(
                judge.at >= since,
                judge.at < until,
                judge.cost.is_not(None),
                judge.cost < float("inf"),
            ),
        ).subquery()
        spent = await self._session.scalar(select(func.sum(rows.c.cost)))
        return float(spent) if spent is not None else None

    async def records(self, repository: str, set_name: str) -> list[EvalRecord]:
        """The set's records, oldest first, each with its task runs."""
        rows = list(
            await self._session.scalars(
                select(EvalRecordRow)
                .where(EvalRecordRow.repository == repository, EvalRecordRow.set_name == set_name)
                .order_by(EvalRecordRow.id)
            )
        )
        runs = await self._session.scalars(
            select(EvalTaskRunRow)
            .where(EvalTaskRunRow.record_id.in_([r.id for r in rows]))
            .order_by(EvalTaskRunRow.task_id, EvalTaskRunRow.run_no)
        )
        by_record: dict[int, list[EvalTaskRunRow]] = {}
        for run in runs:
            by_record.setdefault(run.record_id, []).append(run)
        return [_record(row, by_record.get(row.id, [])) for row in rows]

    async def add_answer(  # one row's columns
        self, repository: str, row: AnswerRow, *, log: str, cost: float | None, by: StartedBy
    ) -> None:
        """Store a scorer's answer about a session."""
        self._session.add(
            JudgementRow(
                repository=repository,
                session_id=row.session_id,
                kind="answer",
                at=row.at,
                scorer=row.scorer,
                answer=row.answer.value,
                evidence=row.evidence,
                log=log,
                cost=cost,
                started_by=by.value,
            )
        )
        await self._session.flush()

    async def add_score(  # noqa: PLR0913  # one row's columns
        self,
        repository: str,
        session_id: str,
        score: int,
        findings: list[str],
        at: datetime,
        *,
        log: str,
        cost: float | None,
        by: StartedBy,
    ) -> None:
        """Store the judge's score of a session."""
        self._session.add(
            JudgementRow(
                repository=repository,
                session_id=session_id,
                kind="score",
                at=at,
                score=score,
                findings=findings,
                log=log,
                cost=cost,
                started_by=by.value,
            )
        )
        await self._session.flush()

    async def answers(self, repository: str, since: datetime) -> list[AnswerRow]:
        """Scorer answers of the repository at or after `since`, oldest first."""
        rows = await self._session.scalars(
            select(JudgementRow)
            .where(
                JudgementRow.repository == repository,
                JudgementRow.kind == "answer",
                JudgementRow.at >= since,
            )
            .order_by(JudgementRow.at, JudgementRow.id)
        )
        return [
            AnswerRow(
                session_id=r.session_id,
                scorer=r.scorer or "",
                answer=Answer(r.answer or "unclear"),
                evidence=r.evidence,
                at=r.at,
            )
            for r in rows
        ]

    async def scheduled_spent(self, repository: str, since: datetime) -> float:
        """What scheduled judging of the repository cost since `since`."""
        spent = await self._session.scalar(
            select(func.coalesce(func.sum(JudgementRow.cost), 0.0)).where(
                JudgementRow.repository == repository,
                JudgementRow.started_by == "schedule",
                JudgementRow.at >= since,
            )
        )
        return float(spent or 0.0)

    async def claim_day(self, repository: str, day: date, now: datetime) -> bool:
        """Claim the day's scheduled judging; a stale unfinished claim can be taken again."""
        claimed = await self._session.execute(
            pg_insert(JudgeDayRow)
            .values(repository=repository, day=day, claimed_at=now)
            .on_conflict_do_update(
                index_elements=[JudgeDayRow.repository, JudgeDayRow.day],
                set_={"claimed_at": now},
                where=(JudgeDayRow.finished_at.is_(None))
                & (JudgeDayRow.claimed_at < now - STALE_CLAIM),
            )
            .returning(JudgeDayRow.repository)
        )
        return claimed.scalar_one_or_none() is not None

    async def finish_day(self, repository: str, day: date, now: datetime) -> None:
        """Mark the day's judging done."""
        await self._session.execute(
            update(JudgeDayRow)
            .where(JudgeDayRow.repository == repository, JudgeDayRow.day == day)
            .values(finished_at=now)
        )
