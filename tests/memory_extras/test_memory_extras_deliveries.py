"""Which entries a run was given, stored in Postgres."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from code_factory.memory.models import NewMemory
from code_factory.memory.service import MemoryService
from code_factory.memory_extras.models import Delivery
from code_factory.memory_extras.repository import DeliveryRepository
from code_factory.platform.db import UnitOfWork
from memory_extras_values import NOW, OWNER

REPO = "sample"
DAY = timedelta(days=1)


async def entries(memory: MemoryService, *statements: str) -> list[str]:
    return [
        (
            await memory.add(
                NewMemory(repository=REPO, kind="rule", statement=s, source="chat"), by=OWNER
            )
        ).id
        for s in statements
    ]


async def test_a_delivery_is_recorded_once_per_run_and_a_repeat_replaces_nothing(
    uow: UnitOfWork, memory: MemoryService
) -> None:
    (first,) = await entries(memory, "Keep it small")
    async with uow() as session:
        store = DeliveryRepository(session)
        await store.record("run-1", "CF-1", REPO, [Delivery(entry_id=first)], NOW)
        await store.record(
            "run-1", "CF-1", REPO, [Delivery(entry_id=first, left_out=True)], NOW + DAY
        )
        receipts = await store.receipts(REPO)
    assert [(r.entry_id, r.run_id, r.ticket_id, r.at) for r in receipts] == [
        (first, "run-1", "CF-1", NOW)
    ]


async def test_receipts_list_each_run_that_was_given_an_entry_oldest_first(
    uow: UnitOfWork, memory: MemoryService
) -> None:
    one, two = await entries(memory, "Keep it small", "Ship early")
    async with uow() as session:
        store = DeliveryRepository(session)
        await store.record("run-b", "CF-2", REPO, [Delivery(entry_id=one)], NOW + DAY)
        await store.record(
            "run-a", "CF-1", REPO, [Delivery(entry_id=one), Delivery(entry_id=two)], NOW
        )
        receipts = await store.receipts(REPO)
    assert [(r.entry_id, r.run_id) for r in receipts] == [
        (one, "run-a"),
        (two, "run-a"),
        (one, "run-b"),
    ]


async def test_an_entry_cut_by_the_budget_is_stored_but_was_not_received(
    uow: UnitOfWork, memory: MemoryService
) -> None:
    (cut,) = await entries(memory, "Keep it small")
    async with uow() as session:
        store = DeliveryRepository(session)
        await store.record("run-1", "CF-1", REPO, [Delivery(entry_id=cut, left_out=True)], NOW)
        assert await store.receipts(REPO) == []
        assert await store.of_run("run-1") == [Delivery(entry_id=cut, left_out=True)]


async def test_receipts_are_of_one_repository(uow: UnitOfWork, memory: MemoryService) -> None:
    (one,) = await entries(memory, "Keep it small")
    async with uow() as session:
        store = DeliveryRepository(session)
        await store.record("run-1", "CF-1", REPO, [Delivery(entry_id=one)], NOW)
        assert await store.receipts("other") == []


async def test_purging_an_entry_removes_its_deliveries(
    uow: UnitOfWork, memory: MemoryService
) -> None:
    one, two = await entries(memory, "Keep it small", "Ship early")
    async with uow() as session:
        store = DeliveryRepository(session)
        await store.record(
            "run-1", "CF-1", REPO, [Delivery(entry_id=one), Delivery(entry_id=two)], NOW
        )
        await session.execute(
            text("delete from memory_entries where repository = :r and name = :n"),
            {"r": REPO, "n": one},
        )
        assert [r.entry_id for r in await store.receipts(REPO)] == [two]


async def test_a_delivery_of_an_entry_that_is_not_there_is_refused_by_the_database(
    uow: UnitOfWork,
) -> None:
    with pytest.raises(IntegrityError, match=r"fk_memory_deliveries"):
        async with uow() as session:
            await DeliveryRepository(session).record(
                "run-1", "CF-1", REPO, [Delivery(entry_id="2026-01-01-none")], NOW
            )
