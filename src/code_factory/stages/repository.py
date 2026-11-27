"""Queries over the stages tables. Every method runs in the session it is given."""

from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import delete, select, union_all, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import lock_until_commit
from code_factory.stages.models import BranchFacts, FixHalt, FixRound, FixWait, ReviewVerdict
from code_factory.stages.tables import (
    EvidenceChangeRow,
    FixHaltRow,
    FixRoundRow,
    FixWaitRow,
    ReviewVerdictRow,
    StageDeclarationRow,
    StageFactsRow,
)


def _one(done: object) -> bool:
    return int(getattr(done, "rowcount", 0)) == 1


class StageRepository:
    """Facts, declarations, evidence changes, fix rounds and review verdicts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, number: int) -> None:
        """Hold the ticket's lock until the transaction ends.

        What `observe`, `begin_fix_round` and `apply_review` decide for one ticket is decided one
        at a time. A row lock would lock nothing on a ticket with no row yet.
        """
        await lock_until_commit(self._session, f"stages:{number}")

    async def facts_of(self, numbers: Iterable[int]) -> dict[int, StageFactsRow]:
        """The stored facts of these tickets."""
        wanted = list(numbers)
        if not wanted:
            return {}
        # Rows are written by upserts that bypass the session's identity map: read them fresh.
        rows = await self._session.scalars(
            select(StageFactsRow)
            .where(StageFactsRow.ticket_number.in_(wanted))
            .execution_options(populate_existing=True)
        )
        return {row.ticket_number: row for row in rows}

    async def save_facts(self, number: int, branch: str, facts: BranchFacts, now: datetime) -> None:
        """Replace the ticket's facts with what git said."""
        values = {
            "branch": branch,
            "known": facts.known,
            "local": facts.local,
            "pushed": facts.pushed,
            "in_worktree": facts.in_worktree,
            "merged": facts.merged,
            "has_commits": facts.has_commits,
            "untraced": facts.untraced,
            "default_branch": facts.default_branch,
            "head": facts.head,
            "observed_at": now,
        }
        statement = pg_insert(StageFactsRow).values(ticket_number=number, **values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=["ticket_number"], set_=values)
        )

    async def mark_unknown(self, number: int, branch: str, now: datetime) -> None:
        """Say git could not be read: the old placement stays, only its trust goes.

        Without a row read for this branch there is nothing to keep, and none is written: the
        ticket's own record places it until git can be read.
        """
        row = (await self.facts_of([number])).get(number)
        if row is None or row.branch != branch:
            return
        await self._session.execute(
            update(StageFactsRow)
            .where(StageFactsRow.ticket_number == number)
            .values(known=False, observed_at=now)
        )

    async def declared_of(self, numbers: Iterable[int]) -> dict[int, str]:
        """The column declared for each of these tickets that has one."""
        wanted = list(numbers)
        if not wanted:
            return {}
        rows = await self._session.execute(
            select(StageDeclarationRow.ticket_number, StageDeclarationRow.stage).where(
                StageDeclarationRow.ticket_number.in_(wanted)
            )
        )
        return dict(rows.all())

    async def set_declared(self, number: int, stage: str, by: str, now: datetime) -> None:
        """Declare the ticket's column; an empty `stage` clears the declaration."""
        if not stage:
            await self._session.execute(
                delete(StageDeclarationRow).where(StageDeclarationRow.ticket_number == number)
            )
            return
        values = {"stage": stage, "by": by, "at": now}
        statement = pg_insert(StageDeclarationRow).values(ticket_number=number, **values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=["ticket_number"], set_=values)
        )

    async def set_declared_if(
        self, number: int, expect: str, stage: str, by: str, now: datetime
    ) -> bool:
        """Declare `stage` only while the declaration is `expect` (empty: none); whether it did.

        One statement decides and writes, so a declaration made meanwhile is never overwritten.
        """
        row = StageDeclarationRow
        if not expect:
            if not stage:
                held = await self._session.scalar(
                    select(row.stage).where(row.ticket_number == number)
                )
                return held is None
            inserted = await self._session.execute(
                pg_insert(row)
                .values(ticket_number=number, stage=stage, by=by, at=now)
                .on_conflict_do_nothing(index_elements=["ticket_number"])
            )
            return _one(inserted)
        held_by_expect = row.ticket_number == number, row.stage == expect
        if not stage:
            deleted = await self._session.execute(delete(row).where(*held_by_expect))
            return _one(deleted)
        changed = await self._session.execute(
            update(row).where(*held_by_expect).values(stage=stage, by=by, at=now)
        )
        return _one(changed)

    async def last_presence(self, number: int) -> dict[str, bool]:
        """Each stage's latest recorded presence; a stage never recorded is absent from the map."""
        rows = await self._session.execute(
            select(EvidenceChangeRow.stage, EvidenceChangeRow.present)
            .where(EvidenceChangeRow.ticket_number == number)
            .ext(distinct_on(EvidenceChangeRow.stage))
            .order_by(EvidenceChangeRow.stage, EvidenceChangeRow.id.desc())
        )
        return dict(rows.all())

    async def append_changes(
        self, number: int, changes: Sequence[tuple[str, bool]], now: datetime
    ) -> None:
        """Record each `(stage, present)` as a row."""
        self._session.add_all(
            EvidenceChangeRow(ticket_number=number, stage=stage, present=present, at=now)
            for stage, present in changes
        )
        await self._session.flush()

    async def changes(
        self, numbers: Iterable[int] | None, since: datetime | None
    ) -> list[EvidenceChangeRow]:
        """The evidence changes of these tickets (every ticket without `numbers`), oldest first."""
        query = select(EvidenceChangeRow).order_by(EvidenceChangeRow.id)
        if numbers is not None:
            query = query.where(EvidenceChangeRow.ticket_number.in_(list(numbers)))
        if since is not None:
            query = query.where(EvidenceChangeRow.at >= since)
        return list(await self._session.scalars(query))

    async def rounds_of(self, number: int) -> list[FixRound]:
        """The fix rounds the ticket was given, oldest first."""
        rows = await self._session.scalars(
            select(FixRoundRow).where(FixRoundRow.ticket_number == number).order_by(FixRoundRow.id)
        )
        return [
            FixRound(head=r.head, reason=r.reason, review=r.review, run_id=r.run_id, at=r.at)
            for r in rows
        ]

    async def repair_requests(self, numbers: Sequence[int]) -> list[tuple[int, datetime]]:
        """Review returns and the rounds recorded for CI or conflicts, without double counting."""
        review = ReviewVerdictRow
        fix = FixRoundRow
        rows = await self._session.execute(
            union_all(
                select(review.ticket_number, review.at).where(
                    review.ticket_number.in_(numbers), review.outcome == "returned"
                ),
                select(fix.ticket_number, fix.at).where(
                    fix.ticket_number.in_(numbers), fix.reason.in_(("ci", "conflict"))
                ),
            )
        )
        return [(number, at) for number, at in rows]

    async def add_round(  # noqa: PLR0913  # one row's columns
        self, number: int, head: str, reason: str, *, review: str, run_id: str, now: datetime
    ) -> None:
        """Record a round."""
        self._session.add(
            FixRoundRow(
                ticket_number=number, head=head, reason=reason, review=review, run_id=run_id, at=now
            )
        )
        await self._session.flush()

    async def remove_unlaunched_round(self, number: int, run_id: str) -> None:
        """Remove a CI or conflict reservation owned by the run that could not launch."""
        await self._session.execute(
            delete(FixRoundRow).where(
                FixRoundRow.ticket_number == number,
                FixRoundRow.run_id == run_id,
                FixRoundRow.reason.in_(("ci", "conflict")),
            )
        )

    async def halts_of(self, number: int) -> list[FixHalt]:
        """The heads and reasons the rounds ran out on, oldest first."""
        rows = await self._session.scalars(
            select(FixHaltRow).where(FixHaltRow.ticket_number == number).order_by(FixHaltRow.id)
        )
        return [FixHalt(head=r.head, reason=r.reason, rounds=r.rounds, at=r.at) for r in rows]

    async def add_halt(
        self, number: int, head: str, reason: str, rounds: int, now: datetime
    ) -> None:
        """Record that the rounds ran out on `head` for `reason`, once."""
        statement = pg_insert(FixHaltRow).values(
            ticket_number=number, head=head, reason=reason, rounds=rounds, at=now
        )
        await self._session.execute(statement.on_conflict_do_nothing())

    async def waits_of(self, number: int) -> list[FixWait]:
        """The steps the ticket's heads failed on that main fails too."""
        rows = await self._session.scalars(
            select(FixWaitRow).where(FixWaitRow.ticket_number == number).order_by(FixWaitRow.at)
        )
        return [FixWait(head=r.head, step=r.step, main_commit=r.main_commit, at=r.at) for r in rows]

    async def set_wait(
        self, number: int, head: str, step: str, main_commit: str, now: datetime
    ) -> None:
        """Record the step `head` fails on that main fails too; the latest write wins."""
        values = {"step": step, "main_commit": main_commit, "at": now}
        statement = pg_insert(FixWaitRow).values(ticket_number=number, head=head, **values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=["ticket_number", "head"], set_=values)
        )

    async def verdicts_of(self, number: int) -> list[ReviewVerdict]:
        """The ticket's review decisions, oldest first."""
        rows = await self._session.scalars(
            select(ReviewVerdictRow)
            .where(ReviewVerdictRow.ticket_number == number)
            .order_by(ReviewVerdictRow.id)
        )
        return [
            ReviewVerdict(
                run_id=r.run_id,
                outcome=r.outcome,  # ty: ignore[invalid-argument-type]  # the check constraint holds it
                head=r.head,
                reason=r.reason,
                note=r.note,
                at=r.at,
            )
            for r in rows
        ]

    async def review_return_at(self, number: int, by: str) -> datetime | None:
        """The latest effective review's timestamp while its Build declaration still holds."""
        verdict, pin = ReviewVerdictRow, StageDeclarationRow
        latest = (
            select(verdict.outcome, verdict.at)
            .where(verdict.ticket_number == number, verdict.outcome != "skipped")
            .order_by(verdict.id.desc())
            .limit(1)
            .subquery()
        )
        return await self._session.scalar(
            select(pin.at)
            .join(latest, pin.at == latest.c.at)
            .where(
                pin.ticket_number == number,
                pin.stage == "build",
                pin.by == by,
                latest.c.outcome == "returned",
            )
        )

    async def clear_review_return(self, number: int, by: str, at: datetime) -> bool:
        """Clear only the Build declaration made by the observed review return."""
        pin = StageDeclarationRow
        removed = await self._session.execute(
            delete(pin).where(
                pin.ticket_number == number, pin.stage == "build", pin.by == by, pin.at == at
            )
        )
        return _one(removed)

    async def add_verdict(  # noqa: PLR0913  # one row's columns
        self,
        number: int,
        outcome: str,
        *,
        head: str,
        run_id: str,
        why: tuple[str, str],
        now: datetime,
    ) -> None:
        """Record a review decision."""
        self._session.add(
            ReviewVerdictRow(
                ticket_number=number,
                outcome=outcome,
                head=head,
                run_id=run_id,
                reason=why[0],
                note=why[1],
                at=now,
            )
        )
        await self._session.flush()
