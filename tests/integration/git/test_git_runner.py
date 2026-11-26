"""The runner: limits, reaping, concurrency, environment. A shim stands in for git."""

import asyncio
import os
from pathlib import Path

import pytest

from code_factory.git.adapters.runner import GitRunner, child_env
from code_factory.platform.errors import UnavailableError


def shim(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "git-shim"
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path


def alive(pid: int) -> bool:
    assert pid > 1
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_a_command_over_the_timeout_is_killed_with_its_children_and_named(
    tmp_path: Path,
) -> None:
    pids = tmp_path / "pids"
    program = shim(tmp_path, f"sleep 30 &\necho $! >> {pids}\necho $$ >> {pids}\nwait")
    runner = GitRunner(program=program)
    with pytest.raises(UnavailableError, match=r"git log in .* took more than 0\.5 s"):
        await runner.run(tmp_path, ["log"], timeout_s=0.5)
    await asyncio.sleep(0.3)
    assert [alive(int(p)) for p in pids.read_text().split()] == [False, False]


async def test_a_cancelled_command_ends_its_group_and_reraises(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    program = shim(tmp_path, f"sleep 30 &\necho $! >> {pids}\nwait")
    runner = GitRunner(program=program)
    task = asyncio.create_task(runner.run(tmp_path, ["log"]))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if pids.exists() and pids.read_text().strip():
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.3)
    assert not alive(int(pids.read_text().split()[0]))


async def test_output_over_the_cap_is_truncated(tmp_path: Path) -> None:
    runner = GitRunner(program=shim(tmp_path, "yes x"))
    done = await runner.run(tmp_path, ["log"], cap=1000)
    assert done.truncated
    assert not done.ok
    assert len(done.stdout) <= 1000


async def test_nine_concurrent_reads_on_one_repository_never_run_more_than_eight(
    tmp_path: Path,
) -> None:
    log = tmp_path / "log"
    program = shim(tmp_path, f"echo s >> {log}\nsleep 0.4\necho e >> {log}")
    runner = GitRunner(program=program)
    await asyncio.gather(*(runner.run(tmp_path, ["log"]) for _ in range(9)))
    running = peak = 0
    for mark in log.read_text().split():
        running += 1 if mark == "s" else -1
        peak = max(peak, running)
    assert peak == 8


async def test_another_repository_does_not_share_the_semaphore_and_reads_skip_the_ref_lock(
    tmp_path: Path,
) -> None:
    slow = tmp_path / "slow"
    slow.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    program = shim(tmp_path, 'case "$3" in *slow) sleep 1.5;; esac')
    runner = GitRunner(program=program)
    blockers = [asyncio.create_task(runner.run(slow, ["log"])) for _ in range(8)]
    await asyncio.sleep(0.2)
    async with asyncio.timeout(1.0):
        await runner.run(other, ["log"])  # not waiting for repository `slow`
        async with runner.ref_lock(other):
            await runner.run(other, ["log"])  # a read does not take the ref lock
    await asyncio.gather(*blockers)


async def test_a_ref_lock_serialises_writers_of_one_repository(tmp_path: Path) -> None:
    order: list[str] = []

    runner = GitRunner(program=Path("/bin/true"))

    async def locked(name: str) -> None:
        async with runner.ref_lock(tmp_path):
            order.append(f"{name}-in")
            await asyncio.sleep(0.05)
            order.append(f"{name}-out")

    await asyncio.gather(locked("a"), locked("b"))
    assert order == ["a-in", "a-out", "b-in", "b-out"]


def test_the_child_environment_drops_repository_variables_and_fixes_the_locale() -> None:
    base = {"PATH": "/usr/bin:relative:/bin", "GIT_DIR": "/x", "GIT_WORK_TREE": "/y",
            "GIT_INDEX_FILE": "/z", "LANG": "de_DE.UTF-8", "HOME": "/h"}  # fmt: skip
    env = child_env(base)
    assert not {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} & env.keys()
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["LC_ALL"] == "C"
    assert env["PATH"] == "/usr/bin:/bin"
    assert child_env(base, clone_git_dir="/c/.git")["GIT_COMMON_DIR"] == "/c/.git"
    assert "GIT_COMMON_DIR" not in env


async def test_a_started_command_sees_that_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_DIR", "/elsewhere")
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    runner = GitRunner(
        program=shim(tmp_path, 'echo "[$GIT_DIR][$LC_ALL][$GIT_NO_REPLACE_OBJECTS]"')
    )
    assert (await runner.run(tmp_path, ["log"])).stdout.strip() == "[][C][1]"


async def test_a_missing_program_is_one_sentence(tmp_path: Path) -> None:
    runner = GitRunner(program=tmp_path / "no-git")
    with pytest.raises(UnavailableError, match="cannot start"):
        await runner.run(tmp_path, ["log"])
