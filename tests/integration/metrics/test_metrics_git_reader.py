"""The git reader against real git in a temporary repository, and a shim standing in for git."""

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_factory.metrics.adapters import GitReader, GitUnavailableError
from code_factory.metrics.rules.merges import parse_merges
from code_factory.platform.errors import UnavailableError
from git_support import ENV, commit, git, make_repo

DAY = 86400


def dated(when: int) -> dict[str, str]:
    return {"GIT_AUTHOR_DATE": f"{when} +0000", "GIT_COMMITTER_DATE": f"{when} +0000"}


def commit_at(root: Path, when: int, subject: str) -> str:
    """A commit whose author and committer dates are `when`."""
    with patch.dict(ENV, dated(when)):
        return commit(root, subject)


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


def branch_with_merge(root: Path) -> str:
    """ticket/cf-7 holds one commit and merges as pull request 7; returns the merge's hash."""
    git(root, "checkout", "-q", "-b", "ticket/cf-7")
    commit(root, "CF-7: work", **{"work.txt": "w\n"})
    git(root, "checkout", "-q", "main")
    git(
        root,
        "merge",
        "-q",
        "--no-ff",
        "-m",
        "Merge pull request #7 from o/ticket/cf-7",
        "ticket/cf-7",
    )
    return git(root, "rev-parse", "HEAD")


async def test_the_log_is_read_in_the_one_format_the_rules_parse(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    merge = branch_with_merge(root)
    log = await GitReader().log(root, "main", since=0.0)
    assert [(m.commit, m.pull, m.ticket) for m in parse_merges(log, 0.0)] == [(merge, 7, "CF-7")]


async def test_the_log_stops_at_the_since_stamp(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    log = await GitReader().log(root, "main", since=4_000_000_000.0)
    assert log == ""


async def test_a_branch_name_that_looks_like_an_option_is_a_ref_not_a_flag(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    with pytest.raises(GitUnavailableError, match="sample"):
        await GitReader().log(root, "--output=pwned", since=0.0)
    assert not (root / "pwned").exists()


async def test_a_log_of_a_missing_branch_names_the_repository_and_is_an_unavailable_error(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    with pytest.raises(UnavailableError, match="cannot read the log of sample"):
        await GitReader().log(root, "nope", since=0.0)


async def test_the_autonomy_range_lists_the_commits_a_merge_brought_in(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    merge = branch_with_merge(root)
    work = git(root, "rev-parse", "ticket/cf-7")
    start = git(root, "rev-parse", "main~1")
    text = await GitReader().autonomy_range(root, merge)
    assert text is not None
    assert text.split() == [work, start]


async def test_the_autonomy_range_of_a_commit_that_is_not_a_merge_is_none(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    assert await GitReader().autonomy_range(root, git(root, "rev-parse", "HEAD")) is None


async def test_a_branch_was_cut_when_its_reflog_begins(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    with patch.dict(ENV, dated(1_700_500_000)):
        git(root, "branch", "ticket/cf-9")
    with patch.dict(ENV, dated(1_700_700_000)):
        git(root, "checkout", "-q", "ticket/cf-9")
        commit(root, "later")
    assert await GitReader().branch_cut(root, "main", "ticket/cf-9") == 1_700_500_000.0


async def test_with_no_reflog_a_branch_was_cut_at_its_first_commit_of_its_own(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    git(root, "checkout", "-q", "-b", "ticket/cf-9")
    commit_at(root, 1_700_000_000, "one")
    commit_at(root, 1_700_000_500, "two")
    git(root, "reflog", "expire", "--expire=now", "--all")
    assert await GitReader().branch_cut(root, "main", "ticket/cf-9") == 1_700_000_000.0


async def test_a_branch_git_cannot_place_has_no_cut(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    assert await GitReader().branch_cut(root, "main", "ticket/cf-404") is None


async def test_a_branch_name_with_shell_syntax_is_one_argument(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    assert await GitReader().branch_cut(root, "main", f"x; touch {tmp_path}/pwned") is None
    assert not (tmp_path / "pwned").exists()


async def test_the_origin_web_address_comes_from_a_github_remote(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    reader = GitReader()
    assert await reader.origin_web(root) is None  # a local bare repository
    git(root, "remote", "set-url", "origin", "git@github.com:o/r.git")
    assert await reader.origin_web(root) == "https://github.com/o/r"


async def test_a_call_over_its_time_is_killed_with_its_children_and_reaped(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    program = shim(tmp_path, f"sleep 30 &\necho $! >> {pids}\necho $$ >> {pids}\nwait")
    reader = GitReader(str(program), log_timeout_s=0.5)
    with pytest.raises(
        GitUnavailableError, match=r"cannot read the log of repo: it took more than 0\.5 s"
    ):
        await reader.log(tmp_path / "repo", "main", since=0.0)
    await asyncio.sleep(0.3)
    assert [alive(int(p)) for p in pids.read_text().split()] == [False, False]


async def test_output_over_the_cap_is_a_failure_not_a_truncated_log(tmp_path: Path) -> None:
    reader = GitReader(str(shim(tmp_path, "yes x")), output_cap=1000)
    with pytest.raises(GitUnavailableError, match="more than 1000 bytes"):
        await reader.log(tmp_path / "repo", "main", since=0.0)


async def test_a_cancelled_call_ends_its_process_and_reraises(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    reader = GitReader(str(shim(tmp_path, f"sleep 30 &\necho $! >> {pids}\nwait")))
    task = asyncio.create_task(reader.log(tmp_path / "repo", "main", since=0.0))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if pids.exists() and pids.read_text().strip():
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.3)
    assert not alive(int(pids.read_text().split()[0]))


async def test_at_most_the_allowed_number_of_calls_run_at_once(tmp_path: Path) -> None:
    trace = tmp_path / "trace"
    reader = GitReader(
        str(shim(tmp_path, f"echo start >> {trace}\nsleep 0.3\necho end >> {trace}")), concurrency=2
    )
    await asyncio.gather(*(reader.autonomy_range(tmp_path, f"c{n}") for n in range(5)))
    running = peak = 0
    for line in trace.read_text().split():
        running += 1 if line == "start" else -1
        peak = max(peak, running)
    assert peak == 2


async def test_two_passes_of_one_repository_never_overlap(tmp_path: Path) -> None:
    reader = GitReader()
    events: list[str] = []

    async def pass_over(name: str) -> None:
        async with reader.exclusive(tmp_path):
            events.append(f"{name} in")
            await asyncio.sleep(0.05)
            events.append(f"{name} out")

    await asyncio.gather(pass_over("a"), pass_over("b"))
    assert events in (["a in", "a out", "b in", "b out"], ["b in", "b out", "a in", "a out"])


async def test_passes_of_two_repositories_run_side_by_side(tmp_path: Path) -> None:
    reader = GitReader()
    both = asyncio.Barrier(2)

    async def pass_over(root: Path) -> None:
        async with reader.exclusive(root):
            async with asyncio.timeout(2):
                await both.wait()

    await asyncio.gather(pass_over(tmp_path / "a"), pass_over(tmp_path / "b"))


async def test_a_missing_program_is_an_unavailable_error(tmp_path: Path) -> None:
    reader = GitReader(str(tmp_path / "no-such-git"))
    with pytest.raises(GitUnavailableError, match="cannot read the log of repo"):
        await reader.log(tmp_path / "repo", "main", since=0.0)


async def test_a_git_planted_in_an_untrusted_place_on_the_path_is_never_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    planted = tmp_path / "planted"
    planted.mkdir()
    marker = tmp_path / "marker"
    shim_in = planted / "git"
    shim_in.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    shim_in.chmod(0o755)
    monkeypatch.setenv("PATH", f"{planted}{os.pathsep}{os.environ['PATH']}")
    log = await GitReader(places=(tmp_path,)).log(root, "main", since=0.0)
    assert not marker.exists()
    assert log != ""
