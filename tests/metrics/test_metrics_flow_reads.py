"""What the Flow read asks of the other modules, and what it leaves out."""

from pathlib import Path
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

from code_factory.metrics.service import MetricsService
from git_support import ENV, git
from metrics_support import DAY, HOUR, NOW, World, at_time, pull_request, ticket


async def test_an_archived_ticket_is_neither_in_flight_nor_stuck(
    metrics: MetricsService, world: World, root: Path
) -> None:
    with patch.dict(ENV, at_time(NOW - 2 * DAY)):
        git(root, "branch", "ticket/cf-1")
    world.tickets.facts["sample"] = [
        ticket("CF-1", NOW - 3 * DAY, stage="build", branch="ticket/cf-1")
    ]
    await metrics.refresh()
    stuck = await metrics.flow()
    assert (stuck.in_flight, [s.id for s in stuck.stuck]) == (1, ["CF-1"])

    world.tickets.facts["sample"] = [
        ticket("CF-1", NOW - 3 * DAY, stage="build", branch="ticket/cf-1", archived=True)
    ]
    page = await metrics.flow()

    assert (page.in_flight, page.stuck) == (0, [])


async def test_a_read_with_merged_tickets_asks_for_them_their_fixes_and_the_branches_only(
    metrics: MetricsService, world: World, root: Path
) -> None:
    pull_request(root, 1, "ticket/cf-1", NOW - 3 * HOUR)
    world.tickets.facts["sample"] = [
        ticket("CF-1", NOW - DAY),
        ticket("CF-2", NOW - DAY),
        ticket("CF-9", NOW - HOUR, caused_by=("CF-1",)),
    ]
    await metrics.refresh()
    world.tickets.calls.clear()

    page = await metrics.flow()

    assert world.tickets.calls == [
        ("sample", None, ["build", "review"]),
        ("sample", ["CF-1"], None),
    ]
    assert world.tickets.cause_calls == [("sample", ["CF-1"])]
    assert [(m.ticket, m.title, m.fixes) for m in page.merged] == [("CF-1", "Idea CF-1", ["CF-9"])]
