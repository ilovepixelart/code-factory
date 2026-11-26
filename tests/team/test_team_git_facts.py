"""The team module's git reads against a fake `git` script: arguments, parsing, the 15 s cache
with its single flight, a 4 process cap, a failed or slow git, and the output cap."""

import asyncio
import logging
import os
import stat
from pathlib import Path

import pytest

from code_factory.team.adapters import GitFacts

TAGS = "v0.1.0\t100\nv0.2.0\t250.5\nnightly\t300\nbroken line\nname\tnot-a-time\n"
LOG = "300\tCF-7: Build it\n100\tCF-7: requirements\n"


def script(tmp_path: Path, body: str) -> Path:
    """A fake `git` that logs its arguments to `calls` and then runs `body`."""
    path = tmp_path / "fake-git"
    path.write_text(f'#!/bin/sh\necho "$*" >> "{tmp_path}/calls"\n{body}\n', encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_tags_are_parsed_from_the_for_each_ref_lines(tmp_path: Path) -> None:
    git = GitFacts(git=str(script(tmp_path, f"printf '{TAGS}'")))
    found = await git.tags("/repo")
    assert found == [("v0.1.0", 100.0), ("v0.2.0", 250.5), ("nightly", 300.0)]
    assert calls(tmp_path) == [
        "-C /repo for-each-ref refs/tags --format=%(refname:short)%09%(creatordate:unix)"
    ]


async def test_the_first_commit_log_asks_for_commits_since_the_day_of_the_moment(
    tmp_path: Path,
) -> None:
    git = GitFacts(git=str(script(tmp_path, f"printf '{LOG}'")))
    assert await git.first_commit_log("/repo", 1_795_435_200.0) == LOG
    assert calls(tmp_path) == ["-C /repo log --all --since=@1795392000 --format=%at%x09%s --"]


async def test_two_concurrent_reads_of_one_repository_run_one_git(tmp_path: Path) -> None:
    git = GitFacts(git=str(script(tmp_path, "sleep 0.2; printf 'v1\\t5\\n'")))
    first, second = await asyncio.gather(git.tags("/repo"), git.tags("/repo"))
    assert first == second == [("v1", 5.0)]
    assert len(calls(tmp_path)) == 1


async def test_an_answer_is_kept_for_15_seconds_then_read_again(tmp_path: Path) -> None:
    clock = Clock()
    git = GitFacts(git=str(script(tmp_path, "printf 'v1\\t5\\n'")), clock=clock)
    await git.tags("/repo")
    clock.now = 14.9
    await git.tags("/repo")
    assert len(calls(tmp_path)) == 1
    clock.now = 15.0
    await git.tags("/repo")
    assert len(calls(tmp_path)) == 2


async def test_the_log_is_read_again_when_its_day_changes_not_before(tmp_path: Path) -> None:
    git = GitFacts(git=str(script(tmp_path, "printf 'x'")))
    await git.first_commit_log("/repo", 1_795_392_000.0 + 10)
    await git.first_commit_log("/repo", 1_795_392_000.0 + 80_000)
    assert len(calls(tmp_path)) == 1
    await git.first_commit_log("/repo", 1_795_392_000.0 + 90_000)
    assert len(calls(tmp_path)) == 2


async def test_each_repository_is_cached_apart(tmp_path: Path) -> None:
    git = GitFacts(git=str(script(tmp_path, "printf 'v1\\t5\\n'")))
    await git.tags("/a")
    await git.tags("/b")
    assert len(calls(tmp_path)) == 2


async def test_a_failing_git_answers_empty_and_logs_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    git = GitFacts(git=str(script(tmp_path, "echo boom >&2; exit 128")))
    with caplog.at_level(logging.WARNING, logger="code_factory.team.adapters"):
        assert await git.tags("/repo") == []
        assert await git.first_commit_log("/repo", 0.0) == ""
    assert "git for-each-ref failed in /repo (exit 128)" in caplog.text


async def test_a_git_that_does_not_exist_answers_empty_too(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    git = GitFacts(git=str(tmp_path / "no-such-git"))
    with caplog.at_level(logging.WARNING, logger="code_factory.team.adapters"):
        assert await git.tags("/repo") == []
    assert "could not start" in caplog.text


async def test_a_slow_git_is_stopped_at_the_timeout_and_answers_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    git = GitFacts(git=str(script(tmp_path, "exec sleep 30")), timeout=0.2)
    with caplog.at_level(logging.WARNING, logger="code_factory.team.adapters"):
        started = asyncio.get_running_loop().time()
        assert await git.tags("/repo") == []
        assert asyncio.get_running_loop().time() - started < 5
    assert "did not finish within 0.2 s" in caplog.text


async def test_output_beyond_the_cap_answers_empty_and_logs_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    git = GitFacts(git=str(script(tmp_path, "exec yes 'CF-1: x'")), limit=1000, timeout=5)
    started = asyncio.get_running_loop().time()
    with caplog.at_level(logging.WARNING, logger="code_factory.team.adapters"):
        assert await git.first_commit_log("/repo", 0.0) == ""
    assert asyncio.get_running_loop().time() - started < 4  # stopped, not waited for
    assert "git log output passed 1000 bytes in /repo" in caplog.text


async def test_output_of_exactly_the_cap_is_whole_and_logs_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    body = "head -c 1000 /dev/zero | tr '\\0' x"
    git = GitFacts(git=str(script(tmp_path, body)), limit=1000, timeout=5)
    with caplog.at_level(logging.WARNING, logger="code_factory.team.adapters"):
        assert await git.first_commit_log("/repo", 0.0) == "x" * 1000
    assert caplog.text == ""


async def test_output_one_byte_beyond_the_cap_is_refused(tmp_path: Path) -> None:
    body = "head -c 1001 /dev/zero | tr '\\0' x"
    git = GitFacts(git=str(script(tmp_path, body)), limit=1000, timeout=5)
    assert await git.first_commit_log("/repo", 0.0) == ""


async def test_no_more_than_four_gits_run_at_once(tmp_path: Path) -> None:
    body = (
        f'echo start >> "{tmp_path}/events"; sleep 0.3; echo end >> "{tmp_path}/events"; printf x'
    )
    git = GitFacts(git=str(script(tmp_path, body)))
    await asyncio.gather(*(git.first_commit_log(f"/repo{n}", 0.0) for n in range(9)))
    running = peak = 0
    for event in (tmp_path / "events").read_text(encoding="utf-8").split():
        running += 1 if event == "start" else -1
        peak = max(peak, running)
    assert peak == 4


async def test_a_cancelled_read_stops_its_git(tmp_path: Path) -> None:
    git = GitFacts(git=str(script(tmp_path, f'echo $$ > "{tmp_path}/pid"; exec sleep 30')))
    task = asyncio.create_task(git.tags("/repo"))
    pid_file = tmp_path / "pid"
    # polls a file the child writes
    while not pid_file.exists() or not pid_file.read_text(encoding="utf-8").strip():  # noqa: ASYNC110
        await asyncio.sleep(0.02)
    pid = int(pid_file.read_text(encoding="utf-8"))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _gone(pid)


def _gone(pid: int) -> bool:
    assert pid > 1  # a pid from data is never signalled unless it is above 1
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def _ignoring_terminate(tmp_path: Path) -> Path:
    """A git that ignores SIGTERM (inherited across exec) and records its pid."""
    return script(tmp_path, f"trap '' TERM; echo $$ > \"{tmp_path}/pid\"; exec sleep 30")


async def _pid_of(tmp_path: Path) -> int:
    pid_file = tmp_path / "pid"
    # polls a file the child writes
    while not pid_file.exists() or not pid_file.read_text(encoding="utf-8").strip():  # noqa: ASYNC110
        await asyncio.sleep(0.02)
    return int(pid_file.read_text(encoding="utf-8"))


async def test_a_git_that_ignores_terminate_is_killed_after_the_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("code_factory.team.adapters._GRACE", 0.3)
    git = GitFacts(git=str(_ignoring_terminate(tmp_path)), timeout=0.3)
    async with asyncio.timeout(10):
        assert await git.tags("/repo") == []
    assert _gone(int((tmp_path / "pid").read_text(encoding="utf-8")))


async def test_a_second_cancellation_during_the_grace_still_ends_the_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("code_factory.team.adapters._GRACE", 0.5)
    git = GitFacts(git=str(_ignoring_terminate(tmp_path)))
    task = asyncio.create_task(git.tags("/repo"))
    pid = await _pid_of(tmp_path)
    task.cancel()
    await asyncio.sleep(0.1)  # inside the grace, the reap is under way
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(5):
        while not _gone(pid):  # noqa: ASYNC110
            await asyncio.sleep(0.05)
