import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sample_world import World, build_world, write_sample_spool
from sessions_harness import Committed
from sessions_values import golden
from sqlalchemy import text

from code_factory.platform.errors import BadRequestError
from code_factory.sessions.models import Event
from code_factory.sessions.repository import LedgerRepository
from code_factory.sessions.service import SessionService, StreamTiming


async def frames(
    stream: AsyncIterator[str], count: int, stop: asyncio.Event, within_s: float = 5.0
) -> list[str]:
    """The next `count` frames, then the stream is stopped and closed."""
    got: list[str] = []
    async with asyncio.timeout(within_s), contextlib.aclosing(stream) as opened:  # ty: ignore[invalid-argument-type]  # an async generator
        async for frame in opened:
            got.append(frame)
            if len(got) == count:
                stop.set()
                break
    return got


@pytest.fixture
def stream_world(tmp_path: Path) -> World:
    return build_world(tmp_path / "world")


async def ingested(
    committed: Committed, tmp_path: Path, world: World, **options: object
) -> SessionService:
    state_dir = tmp_path / "state"
    write_sample_spool(state_dir / "spool", world)
    service = committed.make(state_dir, **options)
    await service.ingest_once(wait=True)
    return service


@pytest.mark.parametrize(
    "case", golden("streams.golden.json"), ids=["after 0", "after 3", "last id 5"]
)
async def test_a_stream_sends_the_events_past_its_position_in_the_golden_bytes(
    committed: Committed, tmp_path: Path, stream_world: World, case: dict[str, object]
) -> None:
    service = await ingested(committed, tmp_path, stream_world)
    header = case.get("last_event_id")
    after = service.parse_position(case.get("after"), header)  # ty: ignore[invalid-argument-type]
    stop = asyncio.Event()
    got = await frames(service.event_stream(after, stop), int(str(case["events"])), stop)
    assert [stream_world.placeholders(frame) for frame in got] == case["chunks"]


async def test_a_stream_from_zero_sends_every_event_once_in_order_with_full_payloads(
    committed: Committed, tmp_path: Path, stream_world: World
) -> None:
    service = await ingested(committed, tmp_path, stream_world)
    stop = asyncio.Event()
    got = await frames(service.event_stream(0, stop), 43, stop)
    seqs = [int(frame.split("\n", 1)[0].removeprefix("id: ")) for frame in got]
    assert seqs == list(range(1, 44))
    assert json.loads(got[3].split("data: ", 1)[1])["payload"]["tool_input"] == {
        "file_path": "/x/a.py"
    }


def test_after_beats_the_header_and_a_non_integer_is_refused_with_the_bare_sentence() -> None:
    parse = SessionService.parse_position
    assert (parse("3", "5"), parse(None, "5"), parse(None, None), parse("", "7")) == (3, 5, 0, 7)
    with pytest.raises(BadRequestError, match=r"^after must be an integer$"):
        parse("x", None)


async def test_no_read_holds_more_than_1000_events(
    committed: Committed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    spool = state_dir / "spool"
    spool.mkdir(parents=True)
    (spool / "s.jsonl").write_bytes(
        b"".join(
            json.dumps({"session_id": "s", "hook_event_name": "Notification", "n": n}).encode()
            + b"\n"
            for n in range(2500)
        )
    )
    service = committed.make(state_dir)
    await service.ingest_once(wait=True)
    sizes: list[int] = []
    original = LedgerRepository.events_after

    async def spy(self: LedgerRepository, after: int, limit: int) -> list[Event]:
        found = await original(self, after, limit)
        sizes.append(len(found))
        assert limit == 1000
        return found

    monkeypatch.setattr(LedgerRepository, "events_after", spy)
    stop = asyncio.Event()
    got = await frames(service.event_stream(0, stop), 2500, stop, within_s=30)
    assert len(got) == 2500
    assert max(sizes) == 1000
    assert sizes[:3] == [1000, 1000, 500]


async def test_a_new_ingest_wakes_an_open_stream_through_the_notification(
    committed: Committed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = 0
    original = LedgerRepository.events_after

    async def counting(self: LedgerRepository, after: int, limit: int) -> list[Event]:
        nonlocal reads
        reads += 1
        return await original(self, after, limit)

    monkeypatch.setattr(LedgerRepository, "events_after", counting)
    state_dir = tmp_path / "state"
    spool = state_dir / "spool"
    spool.mkdir(parents=True)
    service = committed.make(state_dir, timing=StreamTiming(fallback_s=30.0, keepalive_s=60.0))
    listener = asyncio.create_task(service.run_listen())
    try:
        stop = asyncio.Event()
        reader = asyncio.create_task(frames(service.event_stream(0, stop), 1, stop))
        await asyncio.sleep(0.3)  # the stream is open and quiet; the listener is up
        (spool / "s.jsonl").write_bytes(b'{"session_id":"s","hook_event_name":"Stop"}\n')
        started = time.perf_counter()
        await service.ingest_once(wait=True)
        got = await asyncio.wait_for(reader, 2.0)
        assert time.perf_counter() - started < 1.0
        assert json.loads(got[0].split("data: ", 1)[1])["event"] == "Stop"
        # A stream that was woken waits again: it does not read in a loop.
        service_stop = asyncio.Event()
        again = asyncio.create_task(consume(service.event_stream(1, service_stop)))
        await asyncio.sleep(0.2)
        with (spool / "s.jsonl").open("ab") as handle:
            handle.write(b'{"session_id":"s","hook_event_name":"Stop"}\n')
        await service.ingest_once(wait=True)
        await asyncio.sleep(0.3)
        before = reads
        await asyncio.sleep(0.5)
        assert reads - before <= 1
        service_stop.set()
        await asyncio.wait_for(again, 1.0)
    finally:
        listener.cancel()
        await asyncio.gather(listener, return_exceptions=True)


async def test_with_no_notification_the_fallback_read_still_delivers(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    (state_dir / "spool").mkdir(parents=True)
    service = committed.make(state_dir, timing=StreamTiming(fallback_s=0.3, keepalive_s=60.0))
    stop = asyncio.Event()
    reader = asyncio.create_task(frames(service.event_stream(0, stop), 1, stop))
    await asyncio.sleep(0.1)
    (state_dir / "spool" / "s.jsonl").write_bytes(b'{"session_id":"s","hook_event_name":"Stop"}\n')
    await service.ingest_once(wait=True)
    assert len(await asyncio.wait_for(reader, 3.0)) == 1


async def test_without_a_notification_or_a_short_fallback_nothing_arrives_in_between(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    (state_dir / "spool").mkdir(parents=True)
    service = committed.make(state_dir, timing=StreamTiming(fallback_s=30.0, keepalive_s=60.0))
    stop = asyncio.Event()
    reader = asyncio.create_task(frames(service.event_stream(0, stop), 1, stop))
    await asyncio.sleep(0.1)
    (state_dir / "spool" / "s.jsonl").write_bytes(b'{"session_id":"s","hook_event_name":"Stop"}\n')
    await service.ingest_once(wait=True)
    done, _ = await asyncio.wait({reader}, timeout=0.6)
    assert not done
    stop.set()
    assert await asyncio.wait_for(reader, 1.0) == []


async def test_a_quiet_stream_sends_a_keepalive_frame(committed: Committed, tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    service = committed.make(state_dir, timing=StreamTiming(fallback_s=0.05, keepalive_s=0.2))
    stop = asyncio.Event()
    started = time.perf_counter()
    got = await frames(service.event_stream(0, stop), 2, stop)
    assert got == [": keepalive\n\n", ": keepalive\n\n"]
    assert 0.35 < time.perf_counter() - started < 2.0


async def test_open_streams_finish_within_a_second_of_the_service_shutting_down(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    service = committed.make(state_dir)
    stops = [asyncio.Event() for _ in range(3)]
    readers = [asyncio.create_task(consume(service.event_stream(0, stop))) for stop in stops]
    await asyncio.sleep(0.2)
    assert service.open_streams == 3
    started = time.perf_counter()
    service.shutdown()
    await asyncio.wait_for(asyncio.gather(*readers), 1.0)
    assert time.perf_counter() - started < 1.0
    assert service.open_streams == 0


async def consume(stream: AsyncIterator[str]) -> None:
    async with contextlib.aclosing(stream) as opened:  # ty: ignore[invalid-argument-type]
        async for _ in opened:
            pass


async def test_a_stream_ends_when_its_own_stop_is_set(committed: Committed, tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    service = committed.make(state_dir)
    stop = asyncio.Event()
    reader = asyncio.create_task(consume(service.event_stream(0, stop)))
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.wait_for(reader, 1.0)


async def test_a_client_that_leaves_closes_the_generator_and_frees_its_place(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    service = committed.make(state_dir, timing=StreamTiming(fallback_s=0.05, keepalive_s=0.1))
    stream = service.event_stream(0, asyncio.Event())
    assert await anext(stream) == ": keepalive\n\n"
    assert service.open_streams == 1
    await stream.aclose()  # ty: ignore[missing-attribute]  # an async generator
    assert service.open_streams == 0


async def listener_connections(committed: Committed) -> int:
    async with committed.admin.connect() as connection:
        found = await connection.scalar(
            text("select count(*) from pg_stat_activity where application_name = :name"),
            {"name": committed.listener_name},
        )
    return int(found or 0)


async def wait_for_listener(committed: Committed, want: int) -> None:
    async with asyncio.timeout(10):
        while await listener_connections(committed) != want:  # noqa: ASYNC110  # a fact of the database
            await asyncio.sleep(0.05)


async def test_a_listener_that_drops_and_returns_misses_and_repeats_no_event(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    spool = state_dir / "spool"
    spool.mkdir(parents=True)
    service = committed.make(state_dir, timing=StreamTiming(fallback_s=60.0, keepalive_s=120.0))
    listener = asyncio.create_task(service.run_listen())
    try:
        await wait_for_listener(committed, 1)
        stop = asyncio.Event()
        reader = asyncio.create_task(frames(service.event_stream(0, stop), 2, stop, within_s=15))

        async def add(n: int) -> None:
            with (spool / "s.jsonl").open("ab") as handle:
                handle.write(
                    json.dumps({"session_id": "s", "hook_event_name": "Stop", "n": n}).encode()
                    + b"\n"
                )
            await service.ingest_once(wait=True)

        await add(1)
        await asyncio.sleep(0.3)
        async with committed.admin.connect() as connection:
            await connection.execute(
                text(
                    "select pg_terminate_backend(pid) from pg_stat_activity "
                    "where application_name = :name"
                ),
                {"name": committed.listener_name},
            )
        await add(2)  # while the listener is down
        await wait_for_listener(committed, 1)
        got = await reader  # event 2 arrives by the catch-up read after the reconnection
    finally:
        listener.cancel()
        await asyncio.gather(listener, return_exceptions=True)
    assert [json.loads(f.split("data: ", 1)[1])["payload"]["n"] for f in got] == [1, 2]
