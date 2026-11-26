import os
import stat
from pathlib import Path

import pytest

from code_factory.sessions.adapters import RedactionFile, SpoolLine, SpoolReader, TranscriptReader


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


async def test_the_names_are_the_jsonl_files_in_name_order(tmp_path: Path) -> None:
    for name in ("b.jsonl", "a.jsonl", "_x.jsonl", "notes.txt", "c.jsonl.tmp"):
        write(tmp_path / name, b"")
    assert await SpoolReader(tmp_path).names() == ["_x.jsonl", "a.jsonl", "b.jsonl"]


async def test_a_spool_folder_that_does_not_exist_has_no_names(tmp_path: Path) -> None:
    assert await SpoolReader(tmp_path / "nope").names() == []


async def test_stats_give_size_and_time_and_skip_a_file_that_vanished(tmp_path: Path) -> None:
    write(tmp_path / "a.jsonl", b"12345")
    found = await SpoolReader(tmp_path).stats(["a.jsonl", "gone.jsonl"])
    assert list(found) == ["a.jsonl"]
    assert found["a.jsonl"][0] == 5


async def test_only_whole_lines_are_read_and_a_partial_last_line_waits(tmp_path: Path) -> None:
    write(tmp_path / "s.jsonl", b'{"a":1}\n{"b":2}\n{"c":')
    read = await SpoolReader(tmp_path).read_from("s.jsonl", 0)
    assert read.lines == [SpoolLine(0, b'{"a":1}'), SpoolLine(8, b'{"b":2}')]
    assert read.end == 16


async def test_a_line_completed_later_is_read_from_the_offset_reached(tmp_path: Path) -> None:
    path = write(tmp_path / "s.jsonl", b'{"a":1}\n{"c":')
    reader = SpoolReader(tmp_path)
    first = await reader.read_from("s.jsonl", 0)
    path.write_bytes(path.read_bytes() + b"3}\n")
    second = await reader.read_from("s.jsonl", first.end)
    assert second.lines == [SpoolLine(8, b'{"c":3}')]
    assert second.end == 8 + 8


async def test_a_spool_removed_since_it_was_listed_is_nothing_to_read(tmp_path: Path) -> None:
    read = await SpoolReader(tmp_path).read_from("gone.jsonl", 7)
    assert (read.lines, read.end) == ([], 7)


async def test_nothing_past_the_end_is_nothing_to_read(tmp_path: Path) -> None:
    write(tmp_path / "s.jsonl", b"x\n")
    read = await SpoolReader(tmp_path).read_from("s.jsonl", 2)
    assert (read.lines, read.end) == ([], 2)


async def test_a_line_at_the_limit_is_read_and_one_byte_more_is_rejected_unread(
    tmp_path: Path,
) -> None:
    limit = 1000
    ok = b"a" * limit
    over = b"b" * (limit + 1)
    write(tmp_path / "s.jsonl", ok + b"\n" + over + b"\n" + b'{"z":1}\n')
    reader = SpoolReader(tmp_path, max_line=limit)
    first = await reader.read_from("s.jsonl", 0)
    assert first.lines == [SpoolLine(0, ok)]
    second = await reader.read_from("s.jsonl", first.end)
    assert second.lines == [SpoolLine(limit + 1, b"b" * 200, too_long=True)]
    assert second.end == limit + 1 + limit + 2
    third = await reader.read_from("s.jsonl", second.end)
    assert third.lines == [SpoolLine(second.end, b'{"z":1}')]


async def test_a_long_line_still_being_written_is_left_alone(tmp_path: Path) -> None:
    write(tmp_path / "s.jsonl", b"c" * 5000)
    read = await SpoolReader(tmp_path, max_line=1000).read_from("s.jsonl", 0)
    assert (read.lines, read.end) == ([], 0)


async def test_remove_deletes_the_named_files_and_reports_the_ones_gone(tmp_path: Path) -> None:
    write(tmp_path / "a.jsonl", b"x")
    seen = (tmp_path / "a.jsonl").stat()
    spool = SpoolReader(tmp_path)
    gone = await spool.remove({"a.jsonl": (seen.st_size, seen.st_mtime), "missing.jsonl": (1, 0.0)})
    assert gone == ["a.jsonl", "missing.jsonl"]
    assert not (tmp_path / "a.jsonl").exists()


async def test_remove_keeps_a_file_that_changed_since_it_was_seen(tmp_path: Path) -> None:
    write(tmp_path / "a.jsonl", b"x")
    seen = (tmp_path / "a.jsonl").stat()
    write(tmp_path / "a.jsonl", b"xy")
    assert await SpoolReader(tmp_path).remove({"a.jsonl": (seen.st_size, seen.st_mtime)}) == []
    assert (tmp_path / "a.jsonl").exists()


async def test_the_redaction_file_is_replaced_whole_and_owner_only(tmp_path: Path) -> None:
    redaction = RedactionFile(tmp_path / "state")
    await redaction.write('{"v": 1}')
    await redaction.write('{"v": 2}')
    assert redaction.path.read_text() == '{"v": 2}'
    assert stat.S_IMODE(redaction.path.stat().st_mode) == 0o600
    assert [p.name for p in (tmp_path / "state").iterdir()] == ["redaction.json"]


async def test_a_transcript_is_read_from_an_offset_and_a_missing_one_is_nothing(
    tmp_path: Path,
) -> None:
    path = write(tmp_path / "t.jsonl", b"0123456789")
    reader = TranscriptReader()
    assert await reader.read_chunk(str(path), 4, 3) == b"456"
    assert await reader.read_chunk(str(tmp_path / "no"), 0, 3) == b""
    assert await reader.stat(str(path)) == (10, path.stat().st_mtime_ns)
    assert await reader.stat(str(tmp_path / "no")) is None
    write(tmp_path / "t" / "subagents" / "a.jsonl", b"")
    assert await reader.listdir(str(tmp_path / "t" / "subagents")) == ["a.jsonl"]
    assert await reader.listdir(str(tmp_path / "nope")) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads anything")
async def test_an_unreadable_transcript_reads_as_nothing(tmp_path: Path) -> None:
    path = write(tmp_path / "t.jsonl", b"abc")
    path.chmod(0)
    assert await TranscriptReader().read_chunk(str(path), 0, 3) == b""
