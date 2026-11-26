"""`run_logged`: a shell line with its output in a file and an optional time limit."""

import asyncio
import os
import time
from pathlib import Path

from code_factory.platform.process import run_logged

ENV = {"PATH": "/usr/bin:/bin"}


async def alive(pid: int) -> bool:
    assert pid > 1
    for _ in range(60):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        await asyncio.sleep(0.05)
    return True


def text(path: Path) -> str:
    return path.read_text()


def physical(path: Path) -> Path:
    return path.resolve()


def size(path: Path) -> int:
    return path.stat().st_size


async def test_the_exit_code_and_both_streams_go_to_the_log(tmp_path: Path) -> None:
    log = tmp_path / "deep" / "run.log"
    code = await run_logged("echo out; echo err >&2; exit 3", cwd=tmp_path, log=log, env=ENV)
    assert code == 3
    assert text(log).splitlines() == ["out", "err"]


async def test_the_line_runs_in_the_folder_with_only_the_given_environment(tmp_path: Path) -> None:
    log, real = tmp_path / "run.log", physical(tmp_path)
    await run_logged('printf "%s|%s" "$(pwd -P)" "${HOME-unset}"', cwd=tmp_path, log=log, env=ENV)
    assert text(log) == f"{real}|unset"


async def test_a_line_past_its_limit_gives_none_and_leaves_what_it_wrote(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    started = time.monotonic()
    code = await run_logged("echo started; sleep 30", cwd=tmp_path, log=log, env=ENV, limit_s=0.5)
    assert code is None
    assert time.monotonic() - started < 10
    assert text(log) == "started\n"


async def test_a_signal_death_is_the_negative_signal_number(tmp_path: Path) -> None:
    code = await run_logged("kill -9 $$", cwd=tmp_path, log=tmp_path / "run.log", env=ENV)
    assert code == -9


async def test_output_far_beyond_memory_goes_to_the_file_not_the_process(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    code = await run_logged("yes aaaaaaa | head -c 3000000", cwd=tmp_path, log=log, env=ENV)
    assert (code, size(log)) == (0, 3_000_000)


async def test_a_worker_outliving_a_leader_that_exits_on_sigterm_is_killed_at_the_limit(
    tmp_path: Path,
) -> None:
    log = tmp_path / "run.log"
    pid_file = tmp_path / "pid"
    code = await run_logged(
        f"trap 'exit 0' TERM; sleep 30 & echo $! > {pid_file}; wait",
        cwd=tmp_path,
        log=log,
        env=ENV,
        limit_s=0.5,
    )
    assert code is None
    assert not await alive(int(text(pid_file)))


async def test_a_background_worker_of_a_line_that_exits_by_itself_is_stopped(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "pid"
    code = await run_logged(
        f"sleep 30 & echo $! > {pid_file}; exit 0", cwd=tmp_path, log=tmp_path / "run.log", env=ENV
    )
    assert code == 0
    assert not await alive(int(pid_file.read_text()))


async def test_a_line_killed_by_sighup_is_not_the_contained_refusal_code(tmp_path: Path) -> None:
    code = await run_logged("kill -HUP $$", cwd=tmp_path, log=tmp_path / "run.log", env=ENV)
    assert code == 129
