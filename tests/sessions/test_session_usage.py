import json
from pathlib import Path
from typing import override

import pytest
from sample_world import World
from sessions_harness import Clock
from sessions_values import golden

from code_factory.platform.db import UnitOfWork
from code_factory.sessions.adapters import TranscriptReader
from code_factory.sessions.service import SessionService

pytestmark = pytest.mark.usefixtures("sample")


class CountingReader(TranscriptReader):
    """A reader that counts the transcripts it is asked about and the bytes it hands out."""

    def __init__(self) -> None:
        super().__init__()
        self.stats: list[str] = []
        self.bytes = 0

    @override
    async def stat(self, path: str) -> tuple[int, int] | None:
        self.stats.append(Path(path).name)
        return await super().stat(path)

    @override
    async def read_chunk(self, path: str, offset: int, size: int) -> bytes:
        chunk = await super().read_chunk(path, offset, size)
        self.bytes += len(chunk)
        return chunk


@pytest.fixture
def reader() -> CountingReader:
    return CountingReader()


@pytest.fixture
def usage_sessions(
    uow: UnitOfWork, state_dir: Path, clock: Clock, reader: CountingReader
) -> SessionService:
    return SessionService(uow, state_dir=state_dir, clock=clock, transcripts=reader)


def message(message_id: str, input_tokens: int) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {"id": message_id, "usage": {"input_tokens": input_tokens}},
        }
    )


async def test_the_usage_of_every_session_is_what_the_previous_answer_gave(
    usage_sessions: SessionService,
) -> None:
    await usage_sessions.ingest_once()
    assert await usage_sessions.usage() == golden("usage.golden.json")


async def test_a_named_subset_reads_only_those_transcripts_and_an_unknown_id_is_left_out(
    usage_sessions: SessionService, reader: CountingReader
) -> None:
    await usage_sessions.ingest_once()
    found = await usage_sessions.usage(("s-work", "unknown", "s-block"))
    assert list(found) == ["s-work", "s-block"]
    assert found["s-work"]["input"] == 15
    assert sorted(set(reader.stats)) == ["s-block.jsonl", "s-work.jsonl"]


async def test_subagent_transcripts_add_their_tokens_and_the_cost_stays_the_sessions_own(
    usage_sessions: SessionService,
) -> None:
    await usage_sessions.ingest_once()
    found = (await usage_sessions.usage(("s-sub",)))["s-sub"]
    # By hand: 100 + 1 + 0 input and 1000 + 49500 + 500 output; the notes.txt file is no transcript.
    assert (found["input"], found["output"], found["cache_read"]) == (101, 51000, 950000)
    assert found["cost"] is None


async def write_transcript(world: World, name: str, text: str, *, append: bool = False) -> Path:
    path = world.home / "transcripts" / name
    with path.open("a" if append else "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


async def test_a_transcript_that_did_not_grow_is_not_read_again(
    usage_sessions: SessionService, reader: CountingReader
) -> None:
    await usage_sessions.ingest_once()
    await usage_sessions.usage(("s-work",))
    read = reader.bytes
    again = await usage_sessions.usage(("s-work",))
    assert again["s-work"]["input"] == 15
    assert reader.bytes == read


async def test_a_transcript_that_grew_is_read_from_the_offset_it_was_read_to(
    usage_sessions: SessionService, reader: CountingReader, sample: World
) -> None:
    await usage_sessions.ingest_once()
    await usage_sessions.usage(("s-work",))
    before = reader.bytes
    added = message("m9", 10) + "\n"
    await write_transcript(sample, "s-work.jsonl", added, append=True)
    grown = await usage_sessions.usage(("s-work",))
    assert grown["s-work"]["input"] == 25
    assert reader.bytes - before == len(added.encode())


async def test_a_transcript_made_again_shorter_is_read_from_its_start(
    usage_sessions: SessionService, sample: World
) -> None:
    await usage_sessions.ingest_once()
    await usage_sessions.usage(("s-work",))
    await write_transcript(sample, "s-work.jsonl", message("n", 9) + "\n")
    assert (await usage_sessions.usage(("s-work",)))["s-work"]["input"] == 9


async def test_a_transcript_that_is_not_utf8_counts_for_nothing(
    usage_sessions: SessionService, sample: World
) -> None:
    await usage_sessions.ingest_once()
    assert (await usage_sessions.usage(("s-work",)))["s-work"]["input"] == 15
    path = sample.home / "transcripts" / "s-work.jsonl"
    path.write_bytes(path.read_bytes() + b"\xff\xfe\n")
    found = (await usage_sessions.usage(("s-work",)))["s-work"]
    assert (found["input"], found["output"], found["cost"]) == (0, 0, None)


async def test_a_character_cut_at_the_tail_is_read_once_it_is_whole(
    usage_sessions: SessionService, sample: World
) -> None:
    await usage_sessions.ingest_once()
    whole = (message("q", 4) + "\n").encode() + "é".encode()
    path = sample.home / "transcripts" / "s-idle.jsonl"
    path.write_bytes(whole[:-1])  # the writer stopped between the two bytes of the last character
    assert (await usage_sessions.usage(("s-idle",)))["s-idle"]["input"] == 4
    path.write_bytes(whole + b"\n")
    assert (await usage_sessions.usage(("s-idle",)))["s-idle"]["input"] == 4


async def test_a_line_still_being_written_is_counted_once_it_is_whole(
    usage_sessions: SessionService, sample: World
) -> None:
    await usage_sessions.ingest_once()
    line = message("p", 7)
    path = await write_transcript(sample, "s-idle.jsonl", "")
    await usage_sessions.usage(("s-idle",))  # nothing yet
    path.write_text(line[:20])
    assert (await usage_sessions.usage(("s-idle",)))["s-idle"]["input"] == 0
    path.write_text(line + "\n")
    assert (await usage_sessions.usage(("s-idle",)))["s-idle"]["input"] == 7
    assert sample.root.is_dir()


async def test_a_transcript_bigger_than_a_chunk_is_read_in_pieces_cut_at_a_line_break(
    uow: UnitOfWork, state_dir: Path, clock: Clock, sample: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("code_factory.sessions.service.usage.TRANSCRIPT_CHUNK_BYTES", 64)
    service = SessionService(uow, state_dir=state_dir, clock=clock)
    await service.ingest_once()
    lines = "".join(message(f"id{n}", 1) + "\n" for n in range(40))
    await write_transcript(sample, "s-idle.jsonl", lines)
    assert (await service.usage(("s-idle",)))["s-idle"]["input"] == 40


async def test_the_least_recently_read_transcripts_are_forgotten_past_the_bound(
    uow: UnitOfWork, state_dir: Path, clock: Clock, reader: CountingReader, sample: World
) -> None:
    await write_transcript(sample, "s-idle.jsonl", message("i", 3) + "\n")
    service = SessionService(
        uow, state_dir=state_dir, clock=clock, transcripts=reader, kept_transcripts=2
    )
    await service.ingest_once()
    for session_id in ("s-work", "s-block", "s-idle"):
        await service.usage((session_id,))
    service.maintain()
    reader.bytes = 0
    assert (await service.usage(("s-idle",)))["s-idle"]["input"] == 3
    assert reader.bytes == 0
    await service.usage(("s-work",))
    assert reader.bytes > 0
