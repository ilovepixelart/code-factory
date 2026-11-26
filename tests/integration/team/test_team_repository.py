"""Claims in Postgres: the unique ticket, the cascade, run ids, and float to timestamptz."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.team.repository import LeaseRepository
from code_factory.tickets.models import Ticket
from team_values import NOW


async def count(session: AsyncSession, table: str) -> int:
    found = (await session.execute(text(f"select count(*) from {table}"))).scalar_one()  # noqa: S608
    return int(found)


async def test_a_claim_is_stored_with_its_agent_and_times_and_read_back_as_seconds(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    repo = LeaseRepository(db_session)
    await repo.add(ticket.number, "writer", NOW)
    stored = await repo.all()
    lease = stored[ticket.id]
    assert (lease.agent, lease.runs, lease.claimed_at, lease.beat_at) == ("writer", (), NOW, NOW)


async def test_a_second_claim_row_for_a_ticket_is_refused_by_the_unique_ticket(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    repo = LeaseRepository(db_session)
    await repo.add(ticket.number, "writer", NOW)
    with pytest.raises(ConflictError, match=rf"^{ticket.id} already has a claim$"):
        await repo.add(ticket.number, "coder", NOW)
    assert (await repo.all())[ticket.id].agent == "writer"


async def test_a_claim_for_a_ticket_that_does_not_exist_is_not_found(
    db_session: AsyncSession,
) -> None:
    leases = LeaseRepository(db_session)
    with pytest.raises(NotFoundError, match=r"^CF-999999999 does not exist"):
        await leases.add(999_999_999, "writer", NOW)


async def test_deleting_the_ticket_deletes_its_claim_and_the_runs_under_it(
    db_session: AsyncSession,
) -> None:
    # A ticket with history cannot be deleted, so this one is inserted without any.
    number = (
        await db_session.execute(
            text(
                "insert into tickets (repository, title) values ('sample', 'bare') returning number"
            )
        )
    ).scalar_one()
    repo = LeaseRepository(db_session)
    await repo.add(number, "writer", NOW)
    await repo.attach(number, "r1")
    assert (await count(db_session, "team_leases"), await count(db_session, "team_lease_runs")) == (
        1,
        1,
    )
    await db_session.execute(text("delete from tickets where number = :n"), {"n": number})
    assert (await count(db_session, "team_leases"), await count(db_session, "team_lease_runs")) == (
        0,
        0,
    )


async def test_run_ids_attach_once_and_come_back_with_their_claim(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    repo = LeaseRepository(db_session)
    await repo.add(ticket.number, "writer", NOW)
    assert await repo.attach(ticket.number, "r2") is True
    assert await repo.attach(ticket.number, "r1") is True
    assert await repo.attach(ticket.number, "r1") is True
    assert (await repo.all())[ticket.id].runs == ("r1", "r2")
    assert await count(db_session, "team_lease_runs") == 2


async def test_attaching_to_a_ticket_without_a_claim_says_so(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    assert await LeaseRepository(db_session).attach(ticket.number, "r1") is False


async def test_delete_removes_the_claim_and_says_whether_there_was_one(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    repo = LeaseRepository(db_session)
    await repo.add(ticket.number, "writer", NOW)
    await repo.attach(ticket.number, "r1")
    assert await repo.delete(ticket.number) is True
    assert await repo.delete(ticket.number) is False
    assert (await repo.all(), await count(db_session, "team_lease_runs")) == ({}, 0)


async def test_replace_gives_a_fresh_claim_with_no_runs(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    repo = LeaseRepository(db_session)
    await repo.add(ticket.number, "writer", NOW - 500)
    await repo.attach(ticket.number, "r1")
    await repo.replace(ticket.number, "coder", NOW)
    lease = (await repo.all())[ticket.id]
    assert (lease.agent, lease.runs, lease.claimed_at, lease.beat_at) == ("coder", (), NOW, NOW)


async def test_beat_moves_only_the_beat(db_session: AsyncSession, ticket: Ticket) -> None:
    repo = LeaseRepository(db_session)
    await repo.add(ticket.number, "writer", NOW - 30)
    await repo.beat([ticket.number], NOW)
    lease = (await repo.all())[ticket.id]
    assert (lease.claimed_at, lease.beat_at) == (NOW - 30, NOW)


async def test_the_advisory_lock_can_be_taken_twice_by_one_transaction(
    db_session: AsyncSession,
) -> None:
    repo = LeaseRepository(db_session)
    await repo.lock()
    await repo.lock()
