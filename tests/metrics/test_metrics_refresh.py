"""A refresh pass over a real repository: the ledger rows, their flags and the branch cuts."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.metrics.adapters import GitUnavailableError
from code_factory.metrics.models import CheckRecord, RefreshResult
from code_factory.metrics.service import MetricsService
from code_factory.metrics.service import refresh as refresh_module
from code_factory.platform.errors import NotFoundError
from git_support import ENV, git
from metrics_support import (
    DAY,
    HOUR,
    NOW,
    World,
    at_time,
    commit_at,
    pull_request,
    run_facts,
    when,
)

# Four pull requests merged in the window, newest last:
# - #1 CF-1, whose checks passed on its head;
# - #2 CF-2, whose checks failed on its head, reverted by #4;
# - #3 CF-3, checked on another commit only;
# - #4 revert/two, of no ticket, whose commit says it reverts #2.
FIRST = NOW - 4 * HOUR


def held_history(root: Path) -> dict[int, str]:
    """Merge pull requests 1 to 4; the merge commit of each, by number."""
    merges = {}
    for number, branch in enumerate(["ticket/cf-1", "ticket/cf-2", "ticket/cf-3"], start=1):
        merges[number] = pull_request(root, number, branch, FIRST + number * HOUR / 2)
    merges[4] = pull_request(
        root, 4, "revert/two", FIRST + 2 * HOUR, "Revert the work of CF-2\n\nThis reverts #2."
    )
    return merges


def record(ticket_id: str, commit: str, exit_code: int) -> CheckRecord:
    return CheckRecord(ticket_id=ticket_id, commit=commit, exit_code=exit_code, at=when(NOW - HOUR))


async def ledger(session: AsyncSession) -> list[tuple[int, bool, str, str]]:
    rows = await session.execute(
        text("select pull, reverted, checks, autonomy from metrics_merges order by pull")
    )
    return [(row[0], row[1], row[2], row[3]) for row in rows]


async def test_a_pass_records_each_merge_with_its_reverted_flag_and_checks_verdict(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    held_history(root)
    heads = {n: git(root, "rev-parse", f"ticket/cf-{n}") for n in (1, 2)}
    world.checks.records_ = [
        record("CF-1", heads[1], 0),
        record("CF-2", heads[2], 1),
        record("CF-3", git(root, "rev-list", "--max-parents=0", "main"), 0),
    ]

    [result] = await metrics.refresh()

    assert result == RefreshResult(repository="sample", seen=4, inserted=4, reverted=1, cuts=0)
    assert await ledger(db_session) == [
        (1, False, "passed", "unknown"),
        (2, True, "failed", "unknown"),
        (3, False, "none", "unknown"),
        (4, False, "none", "unknown"),
    ]


async def test_a_second_pass_changes_nothing(
    metrics: MetricsService, root: Path, db_session: AsyncSession
) -> None:
    held_history(root)
    await metrics.refresh()
    before = await ledger(db_session)

    [again] = await metrics.refresh()

    assert (again.seen, again.inserted, again.reverted) == (4, 0, 1)
    assert await ledger(db_session) == before


async def test_a_merge_that_arrives_between_passes_is_inserted(
    metrics: MetricsService, root: Path, db_session: AsyncSession
) -> None:
    held_history(root)
    await metrics.refresh()
    pull_request(root, 5, "ticket/cf-5", NOW - HOUR)

    [result] = await metrics.refresh()

    assert (result.seen, result.inserted) == (5, 1)
    assert [row[0] for row in await ledger(db_session)] == [1, 2, 3, 4, 5]


async def test_a_row_whose_merge_left_a_rewritten_history_is_deleted(
    metrics: MetricsService, root: Path, db_session: AsyncSession
) -> None:
    held_history(root)
    await metrics.refresh()
    git(root, "reset", "-q", "--hard", "HEAD~1")  # drops pull request 4

    [result] = await metrics.refresh()

    assert (result.seen, result.inserted) == (3, 0)
    assert [row[0] for row in await ledger(db_session)] == [1, 2, 3]


async def test_a_row_older_than_the_window_is_left_alone(
    metrics: MetricsService, root: Path, db_session: AsyncSession
) -> None:
    held_history(root)
    await db_session.execute(
        text(
            "insert into metrics_merges (repository, commit, head, branch, merged_at, started_at, "
            "refreshed_at, pull) values ('sample', 'old', 'h', 'ticket/cf-0', :at, :at, :at, 99)"
        ),
        {"at": when(NOW - 40 * DAY)},
    )

    await metrics.refresh()

    assert 99 in [row[0] for row in await ledger(db_session)]


async def test_a_reverted_flag_is_rewritten_when_a_later_merge_reverts_it(
    metrics: MetricsService, root: Path, db_session: AsyncSession
) -> None:
    pull_request(root, 1, "ticket/cf-1", FIRST)
    await metrics.refresh()
    assert await ledger(db_session) == [(1, False, "none", "unknown")]

    pull_request(root, 2, "revert/one", FIRST + HOUR, "Revert\n\nThis reverts #1.")
    await metrics.refresh()

    assert await ledger(db_session) == [
        (1, True, "none", "unknown"),
        (2, False, "none", "unknown"),
    ]


async def test_a_reverted_flag_is_cleared_when_the_revert_leaves_the_history(
    metrics: MetricsService, root: Path, db_session: AsyncSession
) -> None:
    first = pull_request(root, 1, "ticket/cf-1", FIRST)
    pull_request(root, 2, "revert/one", FIRST + HOUR, "Revert\n\nThis reverts #1.")
    await metrics.refresh()
    assert [row[1] for row in await ledger(db_session)] == [True, False]

    git(root, "reset", "-q", "--hard", first)  # the revert is force-pushed away
    await metrics.refresh()

    assert await ledger(db_session) == [(1, False, "none", "unknown")]


async def test_the_log_is_parsed_off_the_event_loop(
    metrics: MetricsService, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pull_request(root, 1, "ticket/cf-1", FIRST)
    loop_thread = threading.get_ident()
    ran_in: dict[str, int] = {}

    def watch(name: str, real: Callable[..., Any]) -> Callable[..., Any]:
        def call(*args: Any) -> Any:  # noqa: ANN401
            ran_in[name] = threading.get_ident()
            return real(*args)

        return call

    monkeypatch.setattr(refresh_module, "parse_merges", watch("parse", refresh_module.parse_merges))
    monkeypatch.setattr(
        refresh_module, "reverted_commits", watch("reverted", refresh_module.reverted_commits)
    )

    await metrics.refresh()

    assert set(ran_in) == {"parse", "reverted"}
    assert loop_thread not in ran_in.values()


def three_commit_branch(root: Path, merged_at: float) -> list[str]:
    """ticket/cf-1 holds commits A, H and B, merged as pull request 1; their hashes."""
    git(root, "checkout", "-q", "-b", "ticket/cf-1")
    hashes = [
        commit_at(root, merged_at - 600 + 60 * n, name, **{f"{name}.txt": "w\n"})
        for n, name in enumerate(["A", "H", "B"])
    ]
    git(root, "checkout", "-q", "main")
    with patch.dict(ENV, at_time(merged_at)):
        git(
            root,
            "merge",
            "-q",
            "--no-ff",
            "-m",
            "Merge pull request #1 from o/ticket/cf-1",
            "ticket/cf-1",
        )
    return hashes


async def test_a_merge_whose_commits_all_came_from_runs_is_autonomous(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    a, h, b = three_commit_branch(root, NOW - HOUR)
    world.runs.runs = [
        run_facts("CF-1", NOW - 3 * HOUR, commits=[a, h]),
        run_facts("CF-1", NOW - 2 * HOUR, commits=[b]),
    ]
    await metrics.refresh()
    assert [row[3] for row in await ledger(db_session)] == ["autonomous"]


async def test_a_hand_commit_between_two_runs_makes_the_merge_assisted(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    a, _, b = three_commit_branch(root, NOW - HOUR)
    world.runs.runs = [
        run_facts("CF-1", NOW - 3 * HOUR, commits=[a]),
        run_facts("CF-1", NOW - 2 * HOUR, commits=[b]),
    ]
    await metrics.refresh()
    assert [row[3] for row in await ledger(db_session)] == ["assisted"]


async def test_runs_that_recorded_no_commits_leave_the_merge_unknown(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    three_commit_branch(root, NOW - HOUR)
    world.runs.runs = [run_facts("CF-1", NOW - 3 * HOUR, commits=None)]
    await metrics.refresh()
    assert [row[3] for row in await ledger(db_session)] == ["unknown"]


async def test_a_young_unknown_row_is_classed_once_the_runs_commits_arrive(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    hashes = three_commit_branch(root, NOW - HOUR)
    world.runs.runs = [run_facts("CF-1", NOW - 3 * HOUR, commits=None)]
    await metrics.refresh()
    world.runs.runs = [run_facts("CF-1", NOW - 3 * HOUR, commits=hashes)]

    await metrics.refresh()

    assert [row[3] for row in await ledger(db_session)] == ["autonomous"]


async def test_an_old_unknown_row_is_not_recomputed(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    hashes = three_commit_branch(root, NOW - 2 * DAY)
    world.runs.runs = [run_facts("CF-1", NOW - 3 * DAY, commits=None)]
    await metrics.refresh()
    world.runs.runs = [run_facts("CF-1", NOW - 3 * DAY, commits=hashes)]

    await metrics.refresh()

    assert [row[3] for row in await ledger(db_session)] == ["unknown"]


async def test_a_young_row_with_no_verdict_gets_one_when_the_checks_record_arrives(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    pull_request(root, 1, "ticket/cf-1", NOW - 2 * HOUR)
    await metrics.refresh()
    world.checks.records_ = [record("CF-1", git(root, "rev-parse", "ticket/cf-1"), 0)]

    await metrics.refresh()

    assert [row[2] for row in await ledger(db_session)] == ["passed"]


async def test_a_frozen_verdict_does_not_change_after_a_day(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    pull_request(root, 1, "ticket/cf-1", NOW - 3 * DAY)
    head = git(root, "rev-parse", "ticket/cf-1")
    world.checks.records_ = [record("CF-1", head, 1)]
    await metrics.refresh()
    world.checks.records_ = [record("CF-1", head, 0)]

    await metrics.refresh()

    assert [row[2] for row in await ledger(db_session)] == ["failed"]


async def test_an_unknown_repository_is_not_found(metrics: MetricsService) -> None:
    with pytest.raises(NotFoundError, match="nope"):
        await metrics.refresh("nope")


async def test_one_repository_can_be_refreshed_alone(
    metrics: MetricsService, world: World, tmp_path: Path, db_session: AsyncSession
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    commit_at(other, NOW - 10 * DAY, "Start")
    world.track(other)
    pull_request(other, 1, "ticket/cf-1", NOW - HOUR)

    [result] = await metrics.refresh("other")

    assert (result.repository, result.seen) == ("other", 1)
    count = await db_session.scalar(text("select count(*) from metrics_merges"))
    assert count == 1


async def test_a_repository_whose_git_fails_is_skipped_and_the_others_still_answer(
    metrics: MetricsService, world: World, tmp_path: Path, root: Path
) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()  # not a repository: git fails
    world.repositories.repos.insert(
        0, world.repositories.repos[0].model_copy(update={"name": "broken", "path": broken})
    )
    pull_request(root, 1, "ticket/cf-1", NOW - HOUR)

    results = await metrics.refresh()

    assert [(r.repository, r.seen) for r in results] == [("sample", 1)]


async def test_a_named_repository_whose_git_fails_raises(
    metrics: MetricsService, world: World, tmp_path: Path
) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    world.repositories.repos.append(
        world.repositories.repos[0].model_copy(update={"name": "broken", "path": broken})
    )
    with pytest.raises(GitUnavailableError, match="cannot read the log of broken"):
        await metrics.refresh("broken")
