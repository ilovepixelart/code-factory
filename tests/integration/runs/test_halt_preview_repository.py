import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.runs.models import Halt, PreviewRecord
from code_factory.runs.repository import HaltRepository, PreviewRepository
from code_factory.tickets.models import Ticket
from runs_values import at


async def test_agents_are_not_halted_until_a_halt_is_recorded(db_session: AsyncSession) -> None:
    assert await HaltRepository(db_session).halted() is None


async def test_a_halt_keeps_its_first_time_and_actor(db_session: AsyncSession) -> None:
    halts = HaltRepository(db_session)
    assert await halts.halt("owner", at(0)) is True
    assert await halts.halt("cli", at(5)) is False
    assert await halts.halted() == Halt(halted_at=at(0), by="owner")


async def test_resume_deletes_the_halt_and_is_idempotent(db_session: AsyncSession) -> None:
    halts = HaltRepository(db_session)
    await halts.halt("owner", at(0))
    assert await halts.resume() is True
    assert await halts.resume() is False
    assert await halts.halted() is None


async def test_the_halt_table_holds_one_row_by_name(db_session: AsyncSession) -> None:
    await HaltRepository(db_session).halt("owner", at(0))
    savepoint = db_session.begin_nested()
    statement = text("insert into agent_halt (id, halted_at, by) values (2, now(), 'x')")
    with pytest.raises(IntegrityError, match="ck_agent_halt_single_row"):
        async with savepoint:
            await db_session.execute(statement)


def preview(number: int, port: int = 5001, pgid: int = 4242) -> PreviewRecord:
    return PreviewRecord(
        ticket_id=number,
        repository="sample",
        pgid=pgid,
        pgid_started_at=at(0),
        port=port,
        started_at=at(1),
    )


async def test_a_ticket_has_one_preview_and_a_new_one_replaces_it(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    previews = PreviewRepository(db_session)
    await previews.put(preview(ticket.number, port=5001))
    await previews.put(preview(ticket.number, port=5002, pgid=4343))
    assert await previews.get(ticket.number) == preview(ticket.number, port=5002, pgid=4343)
    assert len(await previews.all()) == 1


async def test_a_deleted_preview_is_gone_and_deleting_again_says_so(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    previews = PreviewRepository(db_session)
    await previews.put(preview(ticket.number))
    assert await previews.delete(ticket.number) is True
    assert await previews.delete(ticket.number) is False
    assert await previews.get(ticket.number) is None


@pytest.mark.parametrize(
    ("pgid", "port", "name"),
    [
        (1, 5001, "ck_run_previews_pgid_above_one"),
        (0, 5001, "ck_run_previews_pgid_above_one"),
        (4242, 1023, "ck_run_previews_port_unprivileged"),
        (4242, 65536, "ck_run_previews_port_unprivileged"),
    ],
)
async def test_the_database_refuses_a_preview_with_a_signalable_pgid_of_one_or_a_bad_port(
    db_session: AsyncSession, ticket: Ticket, pgid: int, port: int, name: str
) -> None:
    savepoint = db_session.begin_nested()
    previews = PreviewRepository(db_session)
    row = preview(ticket.number, port=port, pgid=pgid)
    with pytest.raises(IntegrityError, match=name):
        async with savepoint:
            await previews.put(row)


async def test_a_preview_is_deleted_only_while_it_is_the_one_that_was_checked(
    db_session: AsyncSession, ticket: Ticket
) -> None:
    previews = PreviewRepository(db_session)
    await previews.put(preview(ticket.number, port=5002, pgid=4343))
    assert await previews.delete(ticket.number, pgid=4242) is False
    assert await previews.get(ticket.number) is not None
    assert await previews.delete(ticket.number, pgid=4343) is True
    assert await previews.get(ticket.number) is None
