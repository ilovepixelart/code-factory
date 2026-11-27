import os
import random
from pathlib import Path
from typing import override

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import UnitOfWork
from code_factory.sessions.adapters import CheckoutLocator
from code_factory.sessions.models import Checkout, Event
from code_factory.sessions.repository import LedgerRepository, ViewRepository
from code_factory.sessions.rules import derive
from code_factory.sessions.service import SessionService
from sample_world import World, git
from sessions_harness import Clock
from sessions_values import noisy, spool_lines

VIEW_COLUMNS = (
    "select session_id, state, extract(epoch from last_event_at)::float8, last_seq, window_seq, "
    "cwd, repository, branch, transcript, rules_version, view::text from session_views "
    'order by session_id collate "C"'
)


async def assert_views_are_the_full_rederivation(db: AsyncSession) -> int:
    """Every stored view equals the derivation over all of its session's events."""
    ledger = LedgerRepository(db)
    ids = (await db.execute(text("select distinct session_id from session_events"))).scalars().all()
    for session_id in ids:
        events = await ledger.events_from(session_id)
        derived = derive.derive_unsettled(events)
        assert derived is not None
        stored = await ViewRepository(db).get(session_id)
        assert stored is not None
        assert stored.view.model_dump(exclude={"repository", "branch"}) == derived.model_dump(
            exclude={"repository", "branch"}
        ), session_id
        assert stored.last_seq == events[-1].seq
        starts = [e.seq for e in events if e.name == "SessionStart"]
        assert stored.window_seq == (starts[-1] if starts else events[0].seq)
        assert stored.rules_version == derive.RULES_VERSION
    return len(ids)


@pytest.mark.parametrize("seed", range(6))
async def test_the_stored_view_equals_the_full_rederivation_after_each_of_several_batches(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path, seed: int
) -> None:
    rng = random.Random(seed)  # noqa: S311  # a reproducible batch size
    lines = spool_lines(noisy(seed, 120))
    spool = state_dir / "spool" / "n.jsonl"
    spool.parent.mkdir(parents=True)
    at = 0
    while at < len(lines):
        size = rng.choice([1, 3, 9, 25])
        with spool.open("ab") as handle:
            handle.write(b"".join(lines[at : at + size]))
        at += size
        await sessions.ingest_once()
        assert await assert_views_are_the_full_rederivation(db_session) == 1


@pytest.mark.usefixtures("sample")
async def test_the_stored_views_of_the_sample_equal_the_full_rederivation(
    sessions: SessionService, db_session: AsyncSession
) -> None:
    await sessions.ingest_once()
    assert await assert_views_are_the_full_rederivation(db_session) == 10


async def test_a_session_start_in_a_later_batch_keeps_the_folder_and_transcript_of_before_it(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path
) -> None:
    def line(name: str, **extra: object) -> bytes:
        return spool_lines([Event(0, "s", None, name, 5.0, "s", 0, dict(extra))])[0]

    spool = state_dir / "spool" / "s.jsonl"
    spool.parent.mkdir(parents=True)
    spool.write_bytes(line("UserPromptSubmit", cwd="/a", transcript_path="/t.jsonl", prompt="old"))
    await sessions.ingest_once()
    with spool.open("ab") as handle:
        handle.write(line("SessionStart"))
        handle.write(line("UserPromptSubmit", prompt="new"))
    await sessions.ingest_once()
    stored = await ViewRepository(db_session).get("s")
    assert stored is not None
    assert (stored.view.cwd, stored.view.transcript, stored.view.last_prompt) == (
        "/a",
        "/t.jsonl",
        "new",
    )
    assert await assert_views_are_the_full_rederivation(db_session) == 1


async def test_a_changed_branch_is_seen_once_the_checkout_cache_time_has_passed(
    uow: UnitOfWork, state_dir: Path, clock: Clock, db_session: AsyncSession, world: World
) -> None:
    moment = [100.0]
    service = SessionService(
        uow,
        state_dir=state_dir,
        clock=clock,
        locator=CheckoutLocator(ttl=5.0, monotonic=lambda: moment[0]),
    )
    spool = state_dir / "spool" / "s.jsonl"
    spool.parent.mkdir(parents=True)

    async def prompt(n: int) -> str:
        data = spool_lines(
            [Event(0, "s", None, "UserPromptSubmit", float(n), "s", 0, {"cwd": str(world.root)})]
        )
        with spool.open("ab") as handle:
            handle.write(data[0])
        await service.ingest_once()
        stored = await ViewRepository(db_session).get("s")
        assert stored is not None
        return stored.view.branch

    assert await prompt(1) == "main"
    git(world.root, "checkout", "-q", "-b", "other")
    moment[0] = 104.0
    assert await prompt(2) == "main"
    moment[0] = 106.0
    assert await prompt(3) == "other"


@pytest.mark.usefixtures("sample")
async def test_rebuilding_after_the_rules_version_is_cleared_restores_the_same_rows(
    sessions: SessionService, db_session: AsyncSession
) -> None:
    await sessions.ingest_once()
    before = (await db_session.execute(text(VIEW_COLUMNS))).all()
    await db_session.execute(
        text("update session_views set rules_version = 0, view = '{}'::jsonb, state = 'idle'")
    )
    assert await sessions.rebuild_views(stale_only=True) == 10
    assert (await db_session.execute(text(VIEW_COLUMNS))).all() == before


@pytest.mark.usefixtures("sample")
async def test_a_rebuild_of_only_the_stale_views_leaves_current_ones_and_fills_missing_ones(
    sessions: SessionService, db_session: AsyncSession
) -> None:
    await sessions.ingest_once()
    assert await sessions.rebuild_views(stale_only=True) == 0
    await db_session.execute(text("delete from session_views where session_id in ('s-work', 'zz')"))
    assert await sessions.rebuild_views(stale_only=True, batch=1) == 2
    assert (await db_session.execute(text("select count(*) from session_views"))).scalar_one() == 10
    assert await sessions.rebuild_views(batch=4) == 10


async def test_a_session_view_is_gone_from_the_cache_after_it_is_rebuilt(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path
) -> None:
    spool = state_dir / "spool" / "s.jsonl"
    spool.parent.mkdir(parents=True)
    spool.write_bytes(
        spool_lines([Event(0, "s", None, "UserPromptSubmit", 1.0, "s", 0, {"prompt": "a"})])[0]
    )
    await sessions.ingest_once()
    await sessions.rebuild_views()
    with spool.open("ab") as handle:
        handle.write(spool_lines([Event(0, "s", None, "Stop", 2.0, "s", 0, {})])[0])
    await sessions.ingest_once()
    assert await assert_views_are_the_full_rederivation(db_session) == 1


def prompt_line(n: int) -> bytes:
    """A prompt for n = 1, else a tool call."""
    name = "UserPromptSubmit" if n == 1 else "PreToolUse"
    payload = {"prompt": f"p{n}", "tool_name": "Bash", "tool_use_id": f"t{n}"}
    return spool_lines([Event(0, "s", None, name, float(n), "s", 0, payload)])[0]


async def test_a_cached_window_that_another_ingester_moved_on_is_read_again(
    uow: UnitOfWork, state_dir: Path, clock: Clock, db_session: AsyncSession
) -> None:
    first = SessionService(uow, state_dir=state_dir, clock=clock)
    second = SessionService(uow, state_dir=state_dir, clock=clock)
    spool = state_dir / "spool" / "s.jsonl"
    spool.parent.mkdir(parents=True)

    async def add(service: SessionService, n: int) -> None:
        with spool.open("ab") as handle:
            handle.write(prompt_line(n))
        await service.ingest_once()

    await add(first, 1)
    await add(second, 2)
    await add(first, 3)
    assert await assert_views_are_the_full_rederivation(db_session) == 1
    stored = await ViewRepository(db_session).get("s")
    assert stored is not None
    assert stored.view.turn_tool_calls == 2


class IngestingLocator(CheckoutLocator):
    """Between a rebuild's read and its write, a new event arrives and the ingest takes it."""

    def __init__(self, service: SessionService, spool: Path) -> None:
        super().__init__()
        self.service = service
        self.spool = spool
        self.done = False

    @override
    async def locate(self, cwd: str) -> Checkout | None:
        if not self.done:
            self.done = True
            with self.spool.open("ab") as handle:
                handle.write(prompt_line(9))
            await self.service.ingest_once()
        return await super().locate(cwd)


async def test_a_rebuild_does_not_overwrite_a_view_the_ingest_moved_on_meanwhile(
    uow: UnitOfWork, state_dir: Path, clock: Clock, db_session: AsyncSession
) -> None:
    ingest = SessionService(uow, state_dir=state_dir, clock=clock)
    spool = state_dir / "spool" / "s.jsonl"
    spool.parent.mkdir(parents=True)
    spool.write_bytes(prompt_line(1))
    await ingest.ingest_once()
    rebuilding = SessionService(
        uow, state_dir=state_dir, clock=clock, locator=IngestingLocator(ingest, spool)
    )
    await rebuilding.rebuild_views()
    stored = await ViewRepository(db_session).get("s")
    assert stored is not None
    assert stored.view.current_action is not None
    assert stored.view.current_action.tool_use_id == "t9"


class PruningLocator(CheckoutLocator):
    """Between a rebuild's read and its write, the session's spool is pruned."""

    def __init__(self, pruner: SessionService) -> None:
        super().__init__()
        self.pruner = pruner
        self.done = False

    @override
    async def locate(self, cwd: str) -> Checkout | None:
        if not self.done:
            self.done = True
            await self.pruner.prune_spools(30, apply=True)
        return await super().locate(cwd)


async def test_a_rebuild_does_not_bring_back_the_view_of_a_session_pruned_meanwhile(
    uow: UnitOfWork, state_dir: Path, clock: Clock, db_session: AsyncSession
) -> None:
    spool = state_dir / "spool" / "s.jsonl"
    spool.parent.mkdir(parents=True)
    spool.write_bytes(prompt_line(1))
    ingest = SessionService(uow, state_dir=state_dir, clock=clock)
    await ingest.ingest_once()
    moment = clock.seconds - 40 * 86400
    os.utime(spool, (moment, moment))
    rebuilding = SessionService(
        uow, state_dir=state_dir, clock=clock, locator=PruningLocator(ingest)
    )
    await rebuilding.rebuild_views()
    count = (await db_session.execute(text("select count(*) from session_views"))).scalar_one()
    assert count == 0
