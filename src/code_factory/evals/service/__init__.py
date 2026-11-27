"""The evals module's public API: `EvalService` and `JudgeService`."""

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta

from code_factory.evals.models import (
    AnswerRow,
    Comparison,
    Counts,
    EvalRecord,
    Scorer,
    ScorerFiring,
    ScorerRow,
    StartedBy,
)
from code_factory.evals.ports import Places, Tickets
from code_factory.evals.repository import EvalRepository
from code_factory.evals.rules import compare, counts, due, report_lines, set_name_ok
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError

WEEK = timedelta(days=7)
MONTH = timedelta(days=30)


def utc_now() -> datetime:
    """Now, in UTC."""
    return datetime.now(UTC)


def _set(name: str) -> str:
    if not set_name_ok(name):
        msg = f"{name!r} is not a task set name: letters, digits, dot, dash and underscore"
        raise BadRequestError(msg)
    return name


class EvalService:
    """Suite records: store, report, compare."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def record(self, record: EvalRecord) -> int:
        """Store a suite run; its id."""
        _set(record.set_name)
        async with self._uow() as session:
            return await EvalRepository(session).add_record(record)

    async def measurement_spend(self, since: datetime, until: datetime) -> float | None:
        """Spend backed by measured evaluation costs in this window."""
        async with self._uow() as session:
            return await EvalRepository(session).measurement_spend(since, until)

    async def records(self, repository: str, set_name: str) -> list[EvalRecord]:
        """The set's records, oldest first."""
        async with self._uow() as session:
            return await EvalRepository(session).records(repository, _set(set_name))

    async def report(self, repository: str, set_name: str) -> list[str]:
        """One line per recorded run of the set."""
        return report_lines(await self.records(repository, set_name))

    async def compare(
        self, repository: str, set_name: str, agents: Sequence[str] = ()
    ) -> Comparison:
        """Whether the newest setup loses to the one before it, or agent B to agent A."""
        return compare(await self.records(repository, set_name), agents)


class JudgeService:
    """Session judgements and scorer answers: stored, counted, and filed when they pile up."""

    def __init__(
        self,
        uow: UnitOfWork,
        places: Places,
        tickets: Tickets,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow = uow
        self._places = places
        self._tickets = tickets
        self._clock = clock

    async def record_answer(
        self, repository: str, row: AnswerRow, *, log: str = "", cost: float | None = None,
        by: StartedBy = StartedBy.OWNER,
    ) -> None:  # fmt: skip
        """Store a scorer's answer about a session."""
        async with self._uow() as session:
            await EvalRepository(session).add_answer(repository, row, log=log, cost=cost, by=by)

    async def record_score(  # noqa: PLR0913  # one judgement's fields
        self,
        repository: str,
        session_id: str,
        score: int,
        findings: list[str],
        *,
        log: str = "",
        cost: float | None = None,
        by: StartedBy = StartedBy.OWNER,
    ) -> None:
        """Store the judge's score of a session (1 to 5)."""
        if not 1 <= score <= 5:  # noqa: PLR2004  # the judge's scale
            msg = f"a judgement scores 1 to 5, not {score}"
            raise BadRequestError(msg)
        async with self._uow() as session:
            await EvalRepository(session).add_score(
                repository, session_id, score, findings, self._clock(), log=log, cost=cost, by=by
            )

    async def _answers(self, repository: str, since: datetime) -> list[AnswerRow]:
        async with self._uow() as session:
            return await EvalRepository(session).answers(repository, since)

    async def scorer_table(self) -> list[ScorerRow]:
        """Every tracked repository's scorers with their 7 and 30 day counts and open ticket."""
        now = self._clock()
        rows: list[ScorerRow] = []
        for repository in await self._places.names():
            scorers = await self._places.scorers(repository)
            if not scorers:
                continue
            answers = await self._answers(repository, now - MONTH)
            filed = await self._tickets.filed(repository)
            for scorer in scorers:
                prefix = f"scorer:{scorer.name}@"
                ticket = next((f.id for f in filed if f.open and f.source.startswith(prefix)), "")
                rows.append(
                    ScorerRow(
                        repository=repository,
                        name=scorer.name,
                        question=scorer.question,
                        stage=scorer.stage,
                        sample=scorer.sample,
                        threshold=scorer.threshold,
                        week=counts(answers, scorer.name, now - WEEK),
                        month=counts(answers, scorer.name, now - MONTH),
                        ticket=ticket,
                    )
                )
        return rows

    async def scorer_counts(
        self, since: datetime, until: datetime
    ) -> list[tuple[str, Scorer, Counts]]:
        """Each repository's scorers with their answers in `[since, until)`."""
        found: list[tuple[str, Scorer, Counts]] = []
        for repository in await self._places.names():
            scorers = await self._places.scorers(repository)
            if not scorers:
                continue
            answers = [a for a in await self._answers(repository, since) if a.at < until]
            found += [(repository, s, counts(answers, s.name, since)) for s in scorers]
        return found

    async def scorer_firings(self, repository: str) -> list[ScorerFiring]:
        """The tickets the repository's scorers are due to file; the follower files them."""
        answers = await self._answers(repository, datetime.min.replace(tzinfo=UTC))
        filed = await self._tickets.filed(repository)
        found = [due(s, answers, filed) for s in await self._places.scorers(repository)]
        return [firing for firing in found if firing is not None]

    async def claim_day(self, repository: str, day: date) -> bool:
        """Claim the scheduled judging of the repository for the UTC day."""
        async with self._uow() as session:
            return await EvalRepository(session).claim_day(repository, day, self._clock())

    async def finish_day(self, repository: str, day: date) -> None:
        """Mark the day's scheduled judging done."""
        async with self._uow() as session:
            await EvalRepository(session).finish_day(repository, day, self._clock())

    async def scheduled_spent(self, repository: str) -> float:
        """What scheduled judging of the repository cost this UTC month."""
        now = self._clock()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        async with self._uow() as session:
            return await EvalRepository(session).scheduled_spent(repository, start)


__all__ = ["EvalService", "JudgeService"]
