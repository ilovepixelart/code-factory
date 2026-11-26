"""Taking a change back: once, within 30 seconds, and only while the change still stands.

Expected values: G[24], G[25], G[29], G[37], G[41], G[69] and the hand-worked guard sentence.
"""

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError, GoneError, NotFoundError
from code_factory.repositories.service import RepositoryService
from code_factory.stages.service import StageService
from code_factory.ticket_writes.service import TicketWriteService, WritePorts
from code_factory.tickets.models import TicketFields
from code_factory.tickets.service import ActivityService, TicketService
from code_factory.undo.service import UndoService
from stage_fakes import FakeClock, FakeFacts
from write_fakes import build
from write_values import address, exactly, file

OWNER = "owner:owner"
OTHER = "agent:run-1"
GONE = "nothing to undo any more"


async def archived(
    writes: TicketWriteService, tickets: TicketService, title: str = "One"
) -> tuple[str, str]:
    one = await file(tickets, title)
    answer = await writes.update(address(one), {"archived": "true"}, OWNER)
    assert answer.undo is not None
    return one.id, answer.undo


async def test_an_undo_takes_the_change_back_once_and_records_it_as_the_undoers_edit(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService, activity: ActivityService
) -> None:
    ticket, token = await archived(writes, tickets)

    answer = await undo.undo(token, OTHER)

    assert (answer.notice, answer.undo) == ("", None)
    assert (await tickets.get(ticket)).archived is False
    last = (await activity.list_activity(ticket)).items[-1]
    assert (last.kind, last.by) == ("restored", OTHER)
    with pytest.raises(GoneError, match=exactly(f"{GONE}")):
        await undo.undo(token, OWNER)


async def test_an_unknown_token_is_gone(undo: UndoService, writes: TicketWriteService) -> None:
    del writes
    with pytest.raises(GoneError, match=exactly(f"{GONE}")):
        await undo.undo("0" * 32, OWNER)


async def test_an_undo_works_at_thirty_seconds_and_is_gone_a_second_after(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService, clock: FakeClock
) -> None:
    _, on_time = await archived(writes, tickets, "On time")
    ticket, late = await archived(writes, tickets, "Late")

    clock.advance(30)
    await undo.undo(on_time, OWNER)
    clock.advance(1)
    with pytest.raises(GoneError, match=exactly(f"{GONE}")):
        await undo.undo(late, OWNER)

    assert (await tickets.get(ticket)).archived is True


async def test_an_undo_refuses_when_the_guarded_field_changed_since(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    ticket, token = await archived(writes, tickets)
    await tickets.unarchive(ticket, by=OTHER)
    await tickets.archive(ticket, by=OTHER)
    await tickets.unarchive(ticket, by=OTHER)

    with pytest.raises(ConflictError) as refused:
        await undo.undo(token, OWNER)

    assert str(refused.value) == (
        f"{ticket} archived changed since: it is  now, not true as the change left it"
    )
    with pytest.raises(GoneError, match=exactly(f"{GONE}")):
        await undo.undo(token, OWNER)


async def test_a_bulk_undo_is_all_or_nothing(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    first = await file(tickets, "First", priority="medium")
    second = await file(tickets, "Second", "second", priority="medium")
    answer = await writes.bulk([address(first), address(second)], "priority", "low", OWNER)
    assert answer.undo is not None
    await tickets.update(second.id, TicketFields(priority="urgent"), by=OTHER)

    with pytest.raises(
        ConflictError, match=f"{second.id} priority changed since: it is urgent now"
    ):
        await undo.undo(answer.undo, OWNER)

    assert (await tickets.get(first.id)).priority == "low"
    assert (await tickets.get(second.id)).priority == "urgent"


async def test_a_move_undo_puts_back_the_pin_and_is_not_blocked_by_another_drop(
    writes: TicketWriteService, tickets: TicketService, stages: StageService, undo: UndoService
) -> None:
    held = await tickets.set_branch((await file(tickets, "Held")).id, "feat/held", by=OWNER)
    other = await file(tickets, "Other")
    answer = await writes.move(
        address(held), "spec", [f"sample/{other.id}", f"sample/{held.id}"], OWNER
    )
    assert answer.undo is not None
    await writes.set_rank(address(held), 9, OTHER)

    await undo.undo(answer.undo, OWNER)

    assert (await stages.assess(held.id)).declared == ""
    assert (await tickets.get(held.id)).rank == 0


async def test_a_move_undo_refuses_when_the_pin_changed_since(
    writes: TicketWriteService, tickets: TicketService, stages: StageService, undo: UndoService
) -> None:
    held = await tickets.set_branch((await file(tickets, "Held")).id, "feat/held", by=OWNER)
    answer = await writes.move(address(held), "spec", [], OWNER)
    assert answer.undo is not None
    await stages.declare(held.id, "build", OTHER)

    with pytest.raises(ConflictError) as refused:
        await undo.undo(answer.undo, OWNER)

    assert str(refused.value) == (
        f"{held.id} stage changed since: it is build now, not spec as the change left it"
    )
    assert (await stages.assess(held.id)).declared == "build"


async def test_an_undone_delete_cannot_be_restored_twice(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    one = await file(tickets, "One")
    answer = await writes.delete(address(one), OWNER)
    assert answer.undo is not None
    async with tickets.unit(["sample"], wait=1.0) as unit:
        await unit.restore(address(one))

    with pytest.raises(ConflictError, match=exactly(f"{one.id} was already restored")):
        await undo.undo(answer.undo, OWNER)


async def test_an_undo_of_a_ticket_deleted_since_is_not_found(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    ticket, token = await archived(writes, tickets)
    await writes.delete(address(await tickets.get(ticket)), OWNER)

    with pytest.raises(NotFoundError, match=exactly("no such ticket")):
        await undo.undo(token, OWNER)


async def test_an_undo_survives_a_restart(
    writes: TicketWriteService, tickets: TicketService, uow: UnitOfWork, clock: FakeClock
) -> None:
    ticket, token = await archived(writes, tickets)

    restarted = build(uow, clock, FakeFacts())
    await restarted.undo.undo(token, OWNER)

    assert (await tickets.get(ticket)).archived is False


async def test_one_undo_store_holds_one_revert_handler(
    writes: TicketWriteService, uow: UnitOfWork, clock: FakeClock
) -> None:
    del writes
    built = build(uow, clock, FakeFacts())
    ports = WritePorts(
        tickets=built.tickets,
        stages=built.stages,
        git=built.git,
        repositories=RepositoryService(uow),
    )

    with pytest.raises(ValueError, match=r"tickets\.revert is registered already"):
        TicketWriteService(uow, ports, built.undo)
