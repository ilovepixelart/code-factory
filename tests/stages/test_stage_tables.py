"""The stages tables as the spec names them: unique keys, cascades and named checks, read from the
live database."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import TicketService

AT = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)


async def insert(session: AsyncSession, sql: str, **values: object) -> None:
    async with session.begin_nested():
        await session.execute(text(sql), {"at": AT, **values})


ROUND = (
    "insert into fix_rounds (ticket_number, head, reason, review, at) "
    "values (:n, :head, :reason, :review, :at)"
)
HALT = (
    "insert into fix_halts (ticket_number, head, reason, rounds, at) "
    "values (:n, :head, :reason, :rounds, :at)"
)

COUNTS = {
    "fix_rounds": "select count(*) from fix_rounds where ticket_number = :n",
    "fix_halts": "select count(*) from fix_halts where ticket_number = :n",
    "fix_waits": "select count(*) from fix_waits where ticket_number = :n",
    "stage_facts": "select count(*) from stage_facts where ticket_number = :n",
}


async def test_a_round_is_unique_per_ticket_reason_head_and_review_stamp(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    values = {"n": ticket.number, "head": "h1", "reason": "ci", "review": ""}
    await insert(db_session, ROUND, **values)

    with pytest.raises(IntegrityError, match="uq_fix_rounds_round_given"):
        await insert(db_session, ROUND, **values)
    await insert(db_session, ROUND, **{**values, "head": "h2"})
    await insert(db_session, ROUND, **{**values, "reason": "review", "review": "s1"})
    await insert(db_session, ROUND, **{**values, "reason": "review", "review": "s2"})


async def test_a_halt_is_recorded_once_per_head_and_reason(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    values = {"n": ticket.number, "head": "h1", "reason": "ci", "rounds": 3}
    await insert(db_session, HALT, **values)

    with pytest.raises(IntegrityError, match="uq_fix_halts_halt_recorded"):
        await insert(db_session, HALT, **values)
    with pytest.raises(IntegrityError, match="ck_fix_halts_rounds_not_negative"):
        await insert(db_session, HALT, **{**values, "head": "h2", "rounds": -1})


async def test_a_bad_stage_reason_or_outcome_is_refused_by_a_named_check(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    n = ticket.number
    with pytest.raises(IntegrityError, match="ck_evidence_changes_known_stage"):
        await insert(
            db_session,
            "insert into evidence_changes (ticket_number, stage, present, at) "
            "values (:n, 'done', true, :at)",
            n=n,
        )
    with pytest.raises(IntegrityError, match="ck_fix_rounds_known_reason"):
        await insert(db_session, ROUND, n=n, head="h", reason="tired", review="")
    with pytest.raises(IntegrityError, match="ck_review_verdicts_known_outcome"):
        await insert(
            db_session,
            "insert into review_verdicts (ticket_number, outcome, at) values (:n, 'maybe', :at)",
            n=n,
        )
    with pytest.raises(IntegrityError, match="ck_stage_declarations_known_stage"):
        await insert(
            db_session,
            "insert into stage_declarations (ticket_number, stage, at) values (:n, 'done', :at)",
            n=n,
        )


async def test_every_row_goes_with_its_scratch_ticket(
    db_session: AsyncSession, tickets: TicketService
) -> None:
    scratch = await tickets.create_scratch(
        NewTicket(repository="sample", title="Scratch"), by="owner"
    )
    n = scratch.number
    await insert(db_session, ROUND, n=n, head="h", reason="ci", review="")
    await insert(db_session, HALT, n=n, head="h", reason="ci", rounds=1)
    await insert(
        db_session,
        "insert into fix_waits (ticket_number, head, step, main_commit, at) "
        "values (:n, 'h', 's', 'm', :at)",
        n=n,
    )
    await insert(
        db_session,
        "insert into stage_facts (ticket_number, observed_at) values (:n, :at)",
        n=n,
    )

    await tickets.delete_scratch(scratch.id)

    counts = {name: await db_session.scalar(text(sql), {"n": n}) for name, sql in COUNTS.items()}
    assert counts == dict.fromkeys(COUNTS, 0)
