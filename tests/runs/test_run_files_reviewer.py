import asyncio
import stat
from pathlib import Path

import pytest

from code_factory.runs.adapters.files import read_exit, read_tail, remove, write_atomic
from code_factory.runs.adapters.reviewer import ask_reviewer


def _mode_and_siblings(path: Path) -> tuple[int, list[str]]:
    return stat.S_IMODE(path.stat().st_mode), [p.name for p in path.parent.iterdir()]


async def test_a_tail_starts_at_a_line_start_and_holds_the_last_bytes(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    log.write_text("one\ntwo\nthree\nfour\n")
    assert await read_tail(log, 12) == "three\nfour\n"
    assert await read_tail(log, 11) == "three\nfour\n"
    assert await read_tail(log, 5) == "four\n"
    assert await read_tail(log, 4) == ""


async def test_a_log_shorter_than_the_limit_is_read_whole(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    log.write_text("one\ntwo\n")
    assert await read_tail(log, 1024) == "one\ntwo\n"


async def test_a_missing_log_has_no_tail(tmp_path: Path) -> None:
    assert await read_tail(tmp_path / "none.log", 10) is None


async def test_a_folder_has_no_tail(tmp_path: Path) -> None:
    assert await read_tail(tmp_path, 10) is None


async def test_a_link_is_never_followed(tmp_path: Path) -> None:
    (tmp_path / "secret").write_text("private\n")
    (tmp_path / "run.log").symlink_to(tmp_path / "secret")
    assert await read_tail(tmp_path / "run.log", 100) is None


async def test_the_exit_file_holds_the_code_the_wrapper_wrote(tmp_path: Path) -> None:
    path = tmp_path / "a.exit"
    await write_atomic(path, "-15")
    assert await read_exit(path) == -15


@pytest.mark.parametrize("text", ["", "x", "1.5", "12 13"])
async def test_an_exit_file_that_is_not_a_whole_number_is_no_exit(
    tmp_path: Path, text: str
) -> None:
    path = tmp_path / "a.exit"
    path.write_text(text)
    assert await read_exit(path) is None


async def test_no_exit_file_is_no_exit(tmp_path: Path) -> None:
    assert await read_exit(tmp_path / "none.exit") is None


async def test_an_atomic_write_is_private_and_replaces_the_old_content(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    await write_atomic(path, "old")
    await write_atomic(path, "new")
    assert path.read_text() == "new"
    assert _mode_and_siblings(path) == (0o600, ["s.json"])


async def test_removing_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    path = tmp_path / "a.exit"
    path.write_text("0")
    await remove(path)
    await remove(path)
    assert not path.exists()


async def test_the_reviewer_reads_the_request_on_stdin_and_answers_on_stdout(
    tmp_path: Path,
) -> None:
    said = await ask_reviewer('read line; echo "deny $line"', tmp_path, '{"tool":"Bash"}', 10)
    assert said == (True, 'deny {"tool":"Bash"}\n')


async def test_the_reviewer_exit_status_is_reported(tmp_path: Path) -> None:
    assert await ask_reviewer("echo allow; exit 3", tmp_path, "{}", 10) == (False, "allow\n")


async def test_a_reviewer_past_its_time_is_none_and_its_group_is_gone(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    said = await ask_reviewer(f"(sleep 2; touch {marker}) & sleep 30", tmp_path, "{}", 0.3)
    assert said is None
    await asyncio.sleep(2.5)
    assert not marker.exists()


async def test_a_reviewer_that_cannot_start_is_none(tmp_path: Path) -> None:
    assert await ask_reviewer("true", tmp_path / "missing", "{}", 5) is None


async def test_a_reviewer_sees_the_base_environment_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODE_FACTORY_DATABASE_URL", "postgresql://secret")
    said = await ask_reviewer('echo "[${CODE_FACTORY_DATABASE_URL:-}]"', tmp_path, "{}", 5)
    assert said == (True, "[]\n")


async def test_the_reviewers_output_is_read_to_four_kib_and_no_more(tmp_path: Path) -> None:
    said = await ask_reviewer("head -c 100000 /dev/zero | tr '\\0' a", tmp_path, "{}", 10)
    assert said is not None
    assert len(said[1]) == 4096


async def test_a_reviewer_that_prints_more_than_the_pipe_holds_still_gives_its_verdict(
    tmp_path: Path,
) -> None:
    said = await ask_reviewer(
        "echo allow; head -c 1000000 /dev/zero | tr '\\0' a", tmp_path, "{}", 10
    )
    assert said is not None
    assert said[0] is True
    assert said[1].startswith("allow\n")
    assert len(said[1]) == 4096
