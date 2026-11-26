"""Observing and giving rounds under real concurrency: separate committed sessions, since the
savepoint fixture of the other tests runs everything on one connection and cannot show a race."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text

from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService
from code_factory.stages.repository import StageRepository
from code_factory.stages.service import Ports, StageService
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)
from stage_fakes import FakeClock, FakeFacts


@dataclass
class Rig:
    first: StageService
    second: StageService
    facts: FakeFacts
    uow: UnitOfWork
    ticket: Callable[[], Awaitable[str]]


@pytest.fixture
async def rig(
    settings: Settings,
    migrated: None,  # noqa: ARG001
    tmp_path: Path,
) -> AsyncGenerator[Rig]:
    """Two stage services over committed sessions, as two processes would be, and a factory of
    committed tickets in a tracked repository `race`."""
    engine = create_engine(settings)
    uow = UnitOfWork(create_session_factory(engine))
    tickets = TicketService(uow)
    facts = FakeFacts()
    made: list[int] = []
    root = tmp_path / "race"
    root.mkdir()
    await RepositoryService(uow).track(root)

    def build() -> StageService:
        ports = Ports(
            tickets=tickets,
            reviews=ReviewService(uow),
            activity=ActivityService(uow),
            documents=DocumentService(uow),
            releases=ReleaseService(uow, tickets),
            repositories=RepositoryService(uow),
            settings=SettingsService(uow),
            facts=facts,
        )
        return StageService(uow, ports, clock=FakeClock())

    async def ticket() -> str:
        async with uow() as session:
            row = await session.execute(
                text(
                    "insert into tickets (repository, title, branch) "
                    "values ('race', 'r', 'feat/race') returning number"
                )
            )
            made.append(row.scalar_one())
        return f"CF-{made[-1]}"

    try:
        yield Rig(build(), build(), facts, uow, ticket)
    finally:
        await RepositoryService(uow).untrack(root)
        async with uow() as session:
            for table in ("evidence_changes", "stage_facts", "fix_rounds", "fix_halts"):
                await session.execute(
                    text(f"delete from {table} where ticket_number = any(:made)"),  # noqa: S608
                    {"made": made},
                )
            await session.execute(
                text("delete from tickets where number = any(:made)"), {"made": made}
            )
        await engine.dispose()


async def only_race_ticket(rig: Rig) -> str:
    ticket = await rig.ticket()
    rig.facts.give(ticket, local=True, pushed=True, has_commits=True)
    return ticket


async def count(rig: Rig, table: str, ticket: str) -> int:
    number = int(ticket.removeprefix("CF-"))
    async with rig.uow() as session:
        found = await session.scalar(
            text(f"select count(*) from {table} where ticket_number = :n"),  # noqa: S608
            {"n": number},
        )
    return int(found or 0)


@pytest.fixture
def slow_append(monkeypatch: pytest.MonkeyPatch) -> None:
    """Widen the window between reading a ticket's presence and committing its change."""
    for name in ("append_changes", "add_round"):
        original = getattr(StageRepository, name)

        def slowed(wrapped: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
            async def slowly(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(0.3)
                await wrapped(*args, **kwargs)

            return slowly

        monkeypatch.setattr(StageRepository, name, slowed(original))


@pytest.mark.usefixtures("slow_append")
async def test_two_observers_of_one_ticket_append_each_change_once(rig: Rig) -> None:
    ticket = await only_race_ticket(rig)

    async with asyncio.timeout(20):
        await asyncio.gather(rig.first.observe([ticket]), rig.second.observe([ticket]))

    assert await count(rig, "evidence_changes", ticket) == 2


@pytest.mark.usefixtures("slow_append")
async def test_two_simultaneous_requests_for_one_round_give_it_once(rig: Rig) -> None:
    ticket = await rig.ticket()

    async with asyncio.timeout(20):
        decisions = await asyncio.gather(
            rig.first.begin_fix_round(ticket, "h1", "ci"),
            rig.second.begin_fix_round(ticket, "h1", "ci"),
        )

    assert sorted(d.outcome for d in decisions) == ["given", "started"]
    assert await count(rig, "fix_rounds", ticket) == 1
