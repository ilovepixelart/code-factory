"""The branch cuts a refresh pass records for the tickets in flight."""

from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.metrics.service import MetricsService
from git_support import ENV, git
from metrics_support import DAY, NOW, World, at_time, commit_at, ticket


async def cuts(session: AsyncSession) -> dict[str, float | None]:
    rows = await session.execute(text("select branch, cut_at from metrics_branch_cuts"))
    return {branch: None if cut is None else cut.timestamp() for branch, cut in rows}


def in_flight(world: World, *branches: str) -> None:
    world.tickets.facts["sample"] = [
        ticket(f"CF-{n}", NOW - 5 * DAY, stage="build", branch=branch)
        for n, branch in enumerate(branches, start=1)
    ]


async def test_a_branch_in_flight_was_cut_when_its_reflog_begins(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    with patch.dict(ENV, at_time(NOW - 2 * DAY)):
        git(root, "branch", "ticket/cf-1")
    in_flight(world, "ticket/cf-1")

    [result] = await metrics.refresh()

    assert result.cuts == 1
    assert await cuts(db_session) == {"ticket/cf-1": NOW - 2 * DAY}


async def test_with_no_reflog_a_branch_was_cut_at_its_first_commit_of_its_own(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    git(root, "checkout", "-q", "-b", "ticket/cf-1")
    commit_at(root, NOW - 3 * DAY, "one")
    commit_at(root, NOW - 2 * DAY, "two")
    git(root, "checkout", "-q", "main")
    git(root, "reflog", "expire", "--expire=now", "--all")
    in_flight(world, "ticket/cf-1")

    await metrics.refresh()

    assert await cuts(db_session) == {"ticket/cf-1": NOW - 3 * DAY}


async def test_a_branch_git_cannot_place_is_kept_with_no_time_and_retried(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    in_flight(world, "ticket/cf-1")
    await metrics.refresh()
    assert await cuts(db_session) == {"ticket/cf-1": None}

    with patch.dict(ENV, at_time(NOW - DAY)):
        git(root, "branch", "ticket/cf-1")
    await metrics.refresh()

    assert await cuts(db_session) == {"ticket/cf-1": NOW - DAY}


async def test_a_known_cut_is_not_read_again(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    with patch.dict(ENV, at_time(NOW - DAY)):
        git(root, "branch", "ticket/cf-1")
    in_flight(world, "ticket/cf-1")
    await metrics.refresh()
    git(root, "branch", "-D", "ticket/cf-1")

    [result] = await metrics.refresh()

    assert result.cuts == 0
    assert await cuts(db_session) == {"ticket/cf-1": NOW - DAY}


async def test_the_cut_of_a_branch_that_left_flight_is_deleted(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    git(root, "branch", "ticket/cf-1")
    git(root, "branch", "ticket/cf-2")
    in_flight(world, "ticket/cf-1", "ticket/cf-2")
    await metrics.refresh()
    in_flight(world, "ticket/cf-2")

    await metrics.refresh()

    assert list(await cuts(db_session)) == ["ticket/cf-2"]


async def test_a_ticket_with_no_branch_or_archived_has_no_cut(
    metrics: MetricsService, world: World, db_session: AsyncSession
) -> None:
    world.tickets.facts["sample"] = [
        ticket("CF-1", NOW - DAY, stage="build", branch=""),
        ticket("CF-2", NOW - DAY, stage="build", branch="ticket/cf-2", archived=True),
    ]
    await metrics.refresh()
    assert await cuts(db_session) == {}


async def test_only_the_tickets_in_build_or_review_are_asked_for_their_branches(
    metrics: MetricsService, world: World
) -> None:
    await metrics.refresh()
    assert world.tickets.calls == [("sample", None, ["build", "review"])]
