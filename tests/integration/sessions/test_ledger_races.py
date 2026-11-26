import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Mapping
from pathlib import Path
from typing import override

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import UnavailableError
from code_factory.sessions.adapters import CheckoutLocator, SpoolRead, SpoolReader
from code_factory.sessions.models import Checkout
from code_factory.sessions.repository.ledger import LOCK_KEY
from code_factory.sessions.service import SessionService
from sample_world import World
from sessions_harness import Clock, Committed


def spool_line(session: str, n: int, **extra: object) -> bytes:
    payload = {"session_id": session, "hook_event_name": "Notification", "n": n, **extra}
    return json.dumps(payload).encode() + b"\n"


def write_lines(state_dir: Path, name: str, lines: list[bytes]) -> Path:
    path = state_dir / "spool" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(lines))
    return path


async def scalar(db: AsyncSession, sql: str) -> object:
    return (await db.execute(text(sql))).scalar_one()


async def test_a_partial_last_line_waits_and_is_taken_whole_with_the_same_offsets(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path
) -> None:
    whole = spool_line("s", 1)
    rest = spool_line("s", 2)
    path = write_lines(state_dir, "s.jsonl", [whole, rest[:20]])
    assert (await sessions.ingest_once()).lines == 1
    path.write_bytes(whole + rest)
    assert (await sessions.ingest_once()).lines == 1
    offsets = (
        await db_session.execute(text("select spool_offset from session_events order by seq"))
    ).scalars()
    assert list(offsets) == [0, len(whole)]


async def test_a_line_completed_in_two_appends_is_one_event(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path
) -> None:
    line = spool_line("s", 1)
    path = write_lines(state_dir, "s.jsonl", [line[:10]])
    await sessions.ingest_once()
    path.write_bytes(line[:30])
    await sessions.ingest_once()
    path.write_bytes(line)
    await sessions.ingest_once()
    assert await scalar(db_session, "select count(*) from session_events") == 1


async def test_an_unchanged_spool_is_passed_over_without_a_database_write(
    sessions: SessionService, connection: AsyncConnection, state_dir: Path
) -> None:
    write_lines(state_dir, "s.jsonl", [spool_line("s", 1)])
    await sessions.ingest_once()
    seen: list[str] = []

    def record(_c: object, _cur: object, statement: str, *_rest: object) -> None:
        seen.append(statement.strip().lower())

    event.listen(connection.sync_connection, "before_cursor_execute", record)
    try:
        taken = await sessions.ingest_once()
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", record)
    assert taken.lines == 0
    writes = [
        s
        for s in seen
        if s.startswith(("insert", "update", "delete")) or "pg_notify" in s or "advisory" in s
    ]
    assert writes == []


@pytest.mark.parametrize(
    "stamp",
    ["", ',"_captured_at":"x"', ',"_captured_at":1e300', ',"_captured_at":-5'],
    ids=["absent", "text", "huge", "negative"],
)
async def test_a_captured_time_that_is_unusable_is_the_epoch_and_never_an_insert_error(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path, stamp: str
) -> None:
    line = ('{"session_id":"s","hook_event_name":"Stop"' + stamp + "}\n").encode()
    write_lines(state_dir, "s.jsonl", [line])
    assert (await sessions.ingest_once()).lines == 1
    at = await scalar(
        db_session, "select extract(epoch from captured_at)::float8 from session_events"
    )
    assert at == 0.0


async def test_a_line_over_the_limit_is_rejected_and_the_ones_after_it_are_taken(
    uow: UnitOfWork,
    state_dir: Path,
    clock: Clock,
    db_session: AsyncSession,
) -> None:
    service = SessionService(
        uow, state_dir=state_dir, clock=clock, spool=SpoolReader(state_dir / "spool", max_line=500)
    )
    big = b'{"session_id":"s","pad":"' + b"x" * 600 + b'"}\n'
    write_lines(state_dir, "s.jsonl", [spool_line("s", 1), big, spool_line("s", 2)])
    taken = await service.ingest_once()
    assert (taken.lines, taken.rejects) == (3, 1)
    reject = (
        await db_session.execute(text("select reason, length(head) from session_rejects"))
    ).one()
    assert tuple(reject) == ("line too long", 200)
    assert await scalar(db_session, "select count(*) from session_events") == 2


async def test_a_line_of_eight_mebibytes_and_a_byte_is_rejected_not_read_whole(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path
) -> None:
    big = b'{"session_id":"s","pad":"' + b"x" * (8 * 1024 * 1024) + b'"}\n'
    write_lines(state_dir, "s.jsonl", [big, spool_line("s", 1)])
    taken = await sessions.ingest_once()
    assert (taken.lines, taken.rejects) == (2, 1)
    assert await scalar(db_session, "select reason from session_rejects") == "line too long"


class InterferingReader(SpoolReader):
    """Another ingester takes the spool right after this one has read it."""

    def __init__(self, directory: Path, other: SessionService) -> None:
        super().__init__(directory)
        self.other = other
        self.done = False

    @override
    async def read_from(self, name: str, offset: int) -> SpoolRead:
        read = await super().read_from(name, offset)
        if not self.done and read.lines:
            self.done = True
            await self.other.ingest_once()
        return read


async def test_a_batch_whose_progress_moved_meanwhile_rolls_back_and_duplicates_nothing(
    uow: UnitOfWork,
    state_dir: Path,
    clock: Clock,
    db_session: AsyncSession,
) -> None:
    other = SessionService(uow, state_dir=state_dir, clock=clock)
    ours = SessionService(
        uow, state_dir=state_dir, clock=clock, spool=InterferingReader(state_dir / "spool", other)
    )
    write_lines(state_dir, "s.jsonl", [spool_line("s", 1), spool_line("s", 2)])
    taken = await ours.ingest_once()
    assert taken.lines == 0
    assert await scalar(db_session, "select count(*) from session_events") == 2
    assert (await ours.ingest_once()).lines == 0


async def test_two_ingests_at_once_record_each_line_once_and_seq_has_no_gap(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    lines = [spool_line(f"s{n % 5}", n) for n in range(300)]
    for name in ("a.jsonl", "b.jsonl"):
        write_lines(state_dir, name, lines)
    first, second = committed.make(state_dir), committed.make(state_dir)
    results = await asyncio.gather(first.ingest_once(wait=True), second.ingest_once(wait=True))
    assert sum(r.lines for r in results) == 600
    async with committed.admin.connect() as connection:
        found = (
            await connection.execute(
                text("select seq, spool, spool_offset from session_events order by seq")
            )
        ).all()
    assert [row[0] for row in found] == list(range(1, 601))
    assert len({(row[1], row[2]) for row in found}) == 600


async def test_a_spool_that_shrinks_is_logged_and_not_read_again_from_the_start(
    sessions: SessionService,
    db_session: AsyncSession,
    state_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = write_lines(state_dir, "s.jsonl", [spool_line("s", 1), spool_line("s", 2)])
    await sessions.ingest_once()
    before = await scalar(db_session, "select byte_offset from session_spool_progress")
    path.write_bytes(spool_line("s", 9))
    with caplog.at_level(logging.WARNING):
        taken = await sessions.ingest_once()
    assert taken.lines == 0
    assert "s.jsonl" in caplog.text
    assert await scalar(db_session, "select byte_offset from session_spool_progress") == before
    assert await scalar(db_session, "select count(*) from session_events") == 2


async def test_spools_are_taken_in_name_order_so_seq_follows_it(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path
) -> None:
    for name in ("b.jsonl", "a.jsonl", "_u.jsonl"):
        write_lines(state_dir, name, [spool_line("s", 1)])
    await sessions.ingest_once()
    spools = (
        await db_session.execute(text("select spool from session_events order by seq"))
    ).scalars()
    assert list(spools) == ["_u.jsonl", "a.jsonl", "b.jsonl"]


async def test_a_session_without_a_spool_folder_has_nothing_to_take(
    sessions: SessionService,
) -> None:
    assert (await sessions.ingest_once()).lines == 0


async def test_the_sample_ingested_has_one_view_per_session(
    sessions: SessionService, db_session: AsyncSession, sample: World
) -> None:
    assert sample.root.is_dir()
    await sessions.ingest_once()
    assert await scalar(db_session, "select count(*) from session_views") == 10


async def test_an_ingest_that_finds_the_lock_held_does_nothing_and_one_that_waits_gets_it(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    write_lines(state_dir, "s.jsonl", [spool_line("s", 1)])
    service = committed.make(state_dir)
    async with committed.admin.connect() as holder:
        await holder.execute(text(f"select pg_advisory_lock({LOCK_KEY})"))
        try:
            assert (await service.ingest_once()).lines == 0
            waiting = asyncio.create_task(service.ingest_once(wait=True))
            await asyncio.sleep(0.3)
            assert not waiting.done()
        finally:
            await holder.execute(text(f"select pg_advisory_unlock({LOCK_KEY})"))
        assert (await waiting).lines == 1
    async with committed.admin.connect() as connection:
        found = await connection.scalar(text("select count(*) from session_events"))
    assert found == 1


async def test_an_ingest_that_waits_and_never_gets_the_lock_says_so(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    write_lines(state_dir, "s.jsonl", [spool_line("s", 1)])
    service = committed.make(state_dir, lock_wait_ms=100)
    async with committed.admin.connect() as holder:
        await holder.execute(text(f"select pg_advisory_lock({LOCK_KEY})"))
        try:
            with pytest.raises(UnavailableError, match="another ingest holds the lock"):
                await service.ingest_once(wait=True)
        finally:
            await holder.execute(text(f"select pg_advisory_unlock({LOCK_KEY})"))


async def statements_during(connection: AsyncConnection, work: Awaitable[object]) -> list[str]:
    seen: list[str] = []

    def record(_c: object, _cur: object, statement: str, *_rest: object) -> None:
        seen.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", record)
    try:
        await work
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", record)
    return seen


async def test_an_ingest_with_no_spool_touches_no_table(
    sessions: SessionService, connection: AsyncConnection
) -> None:
    assert await statements_during(connection, sessions.ingest_once()) == []


async def test_the_ingest_task_of_a_process_with_no_spool_never_touches_the_database(
    sessions: SessionService, connection: AsyncConnection
) -> None:
    async def run_for_a_while() -> None:
        task = asyncio.create_task(sessions.run_ingest())
        await asyncio.sleep(0.7)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert await statements_during(connection, run_for_a_while()) == []


async def test_the_ingest_task_checks_the_views_once_a_spool_appears_and_then_takes_it(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    service = committed.make(state_dir)
    task = asyncio.create_task(service.run_ingest())
    try:
        await asyncio.sleep(0.3)
        write_lines(state_dir, "s.jsonl", [spool_line("s", 1)])
        async with asyncio.timeout(5), committed.admin.connect() as connection:
            while await connection.scalar(text("select count(*) from session_views")) == 0:  # noqa: ASYNC110  # a database fact
                await asyncio.sleep(0.05)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    async with committed.admin.connect() as connection:
        assert await connection.scalar(text("select count(*) from session_events")) == 1


def sizes_of(state_dir: Path, *names: str) -> dict[str, int]:
    return {name: (state_dir / "spool" / name).stat().st_size for name in names}


async def test_a_spool_of_many_lines_is_taken_in_batches_and_each_line_once(
    uow: UnitOfWork, state_dir: Path, clock: Clock, db_session: AsyncSession
) -> None:
    service = SessionService(uow, state_dir=state_dir, clock=clock, batch_lines=10)
    write_lines(state_dir, "a.jsonl", [spool_line("a", n) for n in range(35)])
    write_lines(state_dir, "b.jsonl", [spool_line("b", n) for n in range(4)])
    taken = await service.ingest_once()
    assert (taken.lines, taken.sessions) == (39, 2)
    assert await scalar(db_session, "select count(*) from session_events") == 39
    assert (await service.ingest_once()).lines == 0
    progress = (
        await db_session.execute(text("select spool, byte_offset from session_spool_progress"))
    ).all()
    assert dict(progress) == sizes_of(state_dir, "a.jsonl", "b.jsonl")


async def test_a_nul_or_a_lone_surrogate_in_a_prompt_does_not_stop_the_ledger(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path
) -> None:
    nasty = {
        "session_id": "s",
        "hook_event_name": "UserPromptSubmit",
        "prompt": "a\u0000b\ud800c",
        "cwd": "/w\u0000",
        "transcript_path": "/t\ud800",
    }
    spool = write_lines(state_dir, "s.jsonl", [json.dumps(nasty).encode() + b"\n"])
    assert (await sessions.ingest_once()).lines == 1
    spool.write_bytes(spool.read_bytes() + spool_line("s", 2))
    assert (await sessions.ingest_once()).lines == 1
    prompt = await scalar(db_session, "select view->>'last_prompt' from session_views")
    assert prompt == "a�b?c"
    assert await scalar(db_session, "select count(*) from session_events") == 2


async def test_a_text_field_the_ledger_cannot_store_is_a_reject_that_does_not_block_the_rest(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path
) -> None:
    write_lines(
        state_dir,
        "s.jsonl",
        [b'{"session_id": "a\\ud800", "hook_event_name": "Stop"}' + b"\n", spool_line("s", 1)],
    )
    taken = await sessions.ingest_once()
    assert (taken.lines, taken.rejects) == (2, 1)
    reason = await scalar(db_session, "select reason from session_rejects")
    assert reason == "ValueError: a text field holds a NUL or a lone surrogate"


class PruningReader(SpoolReader):
    """The spool is pruned right after this ingester has read lines it has not stored yet."""

    def __init__(self, directory: Path, pruner: SessionService) -> None:
        super().__init__(directory)
        self.pruner = pruner
        self.done = False

    @override
    async def read_from(self, name: str, offset: int) -> SpoolRead:
        read = await super().read_from(name, offset)
        if not self.done and read.lines:
            self.done = True
            await self.pruner.prune_spools(30, apply=True)
        return read


async def test_lines_read_before_their_spool_was_pruned_do_not_come_back_as_rows(
    uow: UnitOfWork, state_dir: Path, clock: Clock, db_session: AsyncSession
) -> None:
    path = write_lines(state_dir, "old.jsonl", [spool_line("old", 1), spool_line("old", 2)])
    moment = clock.seconds - 40 * 86400
    os.utime(path, (moment, moment))
    pruner = SessionService(uow, state_dir=state_dir, clock=clock)
    ingester = SessionService(
        uow, state_dir=state_dir, clock=clock, spool=PruningReader(state_dir / "spool", pruner)
    )
    taken = await ingester.ingest_once()
    assert taken.lines == 0
    assert not path.exists()
    assert await scalar(db_session, "select count(*) from session_events") == 0
    assert await scalar(db_session, "select count(*) from session_views") == 0
    assert await scalar(db_session, "select count(*) from session_spool_progress") == 0


class IngestingBeforeRemoval(SpoolReader):
    """An ingester takes the spool after the prune deleted its rows and before its file goes."""

    def __init__(self, directory: Path, ingester: SessionService) -> None:
        super().__init__(directory)
        self.ingester = ingester

    @override
    async def remove(self, expected: Mapping[str, tuple[int, float]]) -> list[str]:
        await self.ingester.ingest_once()
        return await super().remove(expected)


async def test_rows_an_ingest_adds_between_the_prune_and_the_removal_of_a_file_go_too(
    uow: UnitOfWork, state_dir: Path, clock: Clock, db_session: AsyncSession
) -> None:
    path = write_lines(state_dir, "old.jsonl", [spool_line("old", 1), spool_line("old", 2)])
    moment = clock.seconds - 40 * 86400
    os.utime(path, (moment, moment))
    ingester = SessionService(uow, state_dir=state_dir, clock=clock)
    pruner = SessionService(
        uow,
        state_dir=state_dir,
        clock=clock,
        spool=IngestingBeforeRemoval(state_dir / "spool", ingester),
    )
    await pruner.prune_spools(30, apply=True)
    assert not path.exists()
    for table in ("session_events", "session_views", "session_spool_progress"):
        assert await scalar(db_session, COUNTS[table]) == 0


class LocatorThatLetsAnotherIngesterIn(CheckoutLocator):
    """Another ingester stores a view while this one has asked where its folders are."""

    def __init__(self, other: SessionService, state_dir: Path) -> None:
        super().__init__()
        self.other = other
        self.state_dir = state_dir

    @override
    async def locate(self, cwd: str) -> Checkout | None:
        write_lines(self.state_dir, "y.jsonl", [spool_line("s", 1, cwd="/b")])
        await self.other.ingest_once()
        return Checkout("elsewhere", "x")


class OnlyY(SpoolReader):
    @override
    async def names(self) -> list[str]:
        return [name for name in await super().names() if name == "y.jsonl"]


class FixedLocator(CheckoutLocator):
    @override
    async def locate(self, cwd: str) -> Checkout | None:
        return Checkout("repo-b", "branch-b") if cwd == "/b" else None


async def test_a_view_stored_while_the_folders_were_located_keeps_its_stored_place(
    uow: UnitOfWork, state_dir: Path, clock: Clock, db_session: AsyncSession
) -> None:
    other = SessionService(
        uow,
        state_dir=state_dir,
        clock=clock,
        locator=FixedLocator(),
        spool=OnlyY(state_dir / "spool"),
    )
    ingester = SessionService(
        uow,
        state_dir=state_dir,
        clock=clock,
        locator=LocatorThatLetsAnotherIngesterIn(other, state_dir),
    )
    write_lines(state_dir, "x.jsonl", [spool_line("t", 1, cwd="/x"), spool_line("s", 2)])
    await ingester.ingest_once()
    place = await db_session.execute(
        text("select repository, branch from session_views where session_id = 's'")
    )
    assert place.one() == ("repo-b", "branch-b")


class AppendingBeforeRemoval(SpoolReader):
    """The hook appends a line (a resumed session) after the prune chose the file to remove."""

    @override
    async def remove(self, expected: Mapping[str, tuple[int, float]]) -> list[str]:
        for name in expected:
            with (self._directory / name).open("ab") as spool:
                spool.write(spool_line("old", 3))
        return await super().remove(expected)


async def test_a_spool_that_grew_after_the_prune_chose_it_is_kept_with_its_new_line(
    uow: UnitOfWork, state_dir: Path, clock: Clock, db_session: AsyncSession
) -> None:
    path = write_lines(state_dir, "old.jsonl", [spool_line("old", 1), spool_line("old", 2)])
    moment = clock.seconds - 40 * 86400
    os.utime(path, (moment, moment))
    pruner = SessionService(
        uow,
        state_dir=state_dir,
        clock=clock,
        spool=AppendingBeforeRemoval(state_dir / "spool"),
    )
    await pruner.ingest_once()
    os.utime(path, (moment, moment))
    await pruner.prune_spools(30, apply=True)
    assert path.exists()
    assert len(path.read_bytes().splitlines()) == 3
    taken = await pruner.ingest_once()
    assert taken.lines == 1
    assert await scalar(db_session, "select count(*) from session_events") == 1


COUNTS = {
    name: f"select count(*) from {name}"  # noqa: S608  # a fixed table name of this module
    for name in ("session_events", "session_views", "session_spool_progress")
}
