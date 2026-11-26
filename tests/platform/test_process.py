"""The shared subprocess runner: bounded output, a time limit, and a child that is always reaped."""

import asyncio
import os
import time
from pathlib import Path

import pytest

from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import ProcessResult, checked_group, run_process

SH = "/bin/sh"


def sh(script: str) -> list[str]:
    return [SH, "-c", script]


def written_pid(path: Path) -> int | None:
    """The pid the child wrote, once the whole line is there."""
    text = path.read_text() if path.exists() else ""
    return int(text) if text.endswith("\n") else None


async def alive(pid: int, within_s: float = 3.0) -> bool:
    """Whether `pid` is still running after waiting up to `within_s` for it to go."""
    assert pid > 1  # a pid read from data is only ever probed above 1
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        await asyncio.sleep(0.05)
    return True


async def test_a_finished_command_gives_its_code_and_both_streams() -> None:
    result = await run_process(sh("printf out; printf err >&2; exit 3"))
    assert result == ProcessResult(code=3, stdout=b"out", stderr=b"err")


def test_the_environment_and_folder_are_the_ones_given(tmp_path: Path) -> None:
    result = asyncio.run(
        run_process(
            sh('printf "%s|%s|%s" "$FOO" "${HOME-unset}" "$(pwd -P)"'),
            cwd=tmp_path,
            env={"FOO": "bar", "PATH": "/usr/bin:/bin"},
        )
    )
    assert result.stdout.decode() == f"bar|unset|{tmp_path.resolve()}"


async def test_output_past_the_cap_is_cut_there_and_the_child_is_stopped() -> None:
    started = time.monotonic()
    result = await run_process(sh("yes aaaaaaaa"), output_cap=1000, timeout_s=20)
    assert time.monotonic() - started < 10
    assert (result.truncated, len(result.stdout), result.timed_out) == (True, 1000, False)
    assert result.stdout.startswith(b"aaaaaaaa\naaaaaaaa\n")


async def test_output_exactly_at_the_cap_is_not_truncated() -> None:
    result = await run_process(sh("printf 12345"), output_cap=5)
    assert (result.truncated, result.stdout, result.code) == (False, b"12345", 0)


async def test_a_command_past_its_limit_is_stopped_with_everything_it_started() -> None:
    result = await run_process(sh("sleep 30 & echo $!; wait"), timeout_s=0.5)
    assert (result.timed_out, result.code) == (True, None)
    grandchild = int(result.stdout.split()[0])
    assert not await alive(grandchild)


async def test_a_command_that_ignores_sigterm_is_killed_after_the_grace() -> None:
    script = 'trap "" TERM; echo $$; while :; do sleep 1; done'
    started = time.monotonic()
    result = await run_process(sh(script), timeout_s=0.5, grace_s=0.3)
    assert time.monotonic() - started < 5
    assert (result.timed_out, result.code) == (True, None)
    assert not await alive(int(result.stdout.split()[0]))


async def test_cancelling_the_caller_stops_the_child_and_still_raises_cancelled(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "pid"
    task = asyncio.create_task(run_process(sh(f"echo $$ > {pid_file}; exec sleep 30")))
    async with asyncio.timeout(5):
        while (pid := written_pid(pid_file)) is None:  # noqa: ASYNC110  # a file, not an event
            await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not await alive(pid)


async def test_a_program_that_cannot_start_is_one_sentence() -> None:
    with pytest.raises(UnavailableError) as raised:
        await run_process(["/nonexistent/program", "--x"])
    assert str(raised.value) == "cannot start /nonexistent/program: no such file"


@pytest.mark.parametrize("pid", [-1, 0, 1])
def test_pid_one_zero_and_below_are_refused_as_a_group_to_signal(pid: int) -> None:
    with pytest.raises(ValueError, match=f"refusing to signal process group {pid}"):
        checked_group(pid)


def test_a_group_above_one_is_accepted() -> None:
    assert checked_group(2) == 2


async def test_a_worker_left_by_a_leader_that_already_exited_is_still_stopped() -> None:
    result = await run_process(sh("sleep 30 & echo $!; exit 0"), timeout_s=0.5)
    assert result.timed_out  # the worker holds the output open, so the run is cut by its limit
    assert not await alive(int(result.stdout.split()[0]))


async def test_a_worker_that_does_not_hold_the_pipes_is_stopped_when_the_leader_exits() -> None:
    script = "sleep 30 >/dev/null 2>&1 & echo $!; exit 0"
    result = await run_process(sh(script), timeout_s=5)
    assert result.code == 0
    assert not await alive(int(result.stdout.split()[0]))
