"""The public Gate Timings endpoint samples recent timed check activity."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from code_factory.checks.models import Judged
from code_factory.checks.rules import checks_record
from code_factory.stages.rules import read_log
from code_factory.tickets.models import NewActivity, NewTicket, Ticket
from code_factory.tickets.service import ActivityService, TicketService

ENDPOINT = "/api/gate-timings"
START = datetime(2026, 11, 27, 12, tzinfo=UTC)
TARGET = Judged(head="a" * 40, tree="ticket/sample", tree_id="b" * 40)


async def _append_check(
    activity: ActivityService, ticket: Ticket, at: datetime, log: str, *, slept: bool = False
) -> None:
    data = checks_record(TARGET, int(slept), "checks.log", read_log(log), text=log, slept=slept)
    await activity.append(ticket.id, NewActivity(kind="checks", at=at, data=data), by="owner")


async def _timings(client: httpx.AsyncClient) -> list[dict[str, object]]:
    response = await client.get(ENDPOINT)
    assert response.status_code == 200
    return list(response.json())


@pytest.mark.parametrize(
    "log",
    ["gate: this tree and toolchain have already passed\n", "checks passed\n"],
    ids=["cached-pass", "pass-without-phase-data"],
)
async def test_newer_untimed_checks_do_not_hide_a_timed_run(
    client: httpx.AsyncClient, activity: ActivityService, ticket: Ticket, log: str
) -> None:
    await _append_check(activity, ticket, START, "gate: pytest passed in 12s\n")
    baseline = await _timings(client)
    assert [(row["step"], row["median"], row["runs"]) for row in baseline] == [("pytest", 12, 1)]

    for offset in range(1, 25):
        await _append_check(activity, ticket, START + timedelta(seconds=offset), log)
    assert await _timings(client) == baseline

    await _append_check(activity, ticket, START + timedelta(seconds=25), log)
    ledger = (await activity.records_of([ticket.id], "checks"))[ticket.id]
    assert len(ledger) == 26
    assert ledger[0].data["seconds"] == {"pytest": 12}
    assert all("seconds" not in row.data and "steps" not in row.data for row in ledger[1:])
    assert await _timings(client) == baseline


async def test_sample_limits_eligible_runs_across_tickets_and_drops_sleep_interrupted_runs(
    client: httpx.AsyncClient, activity: ActivityService, ticket: Ticket, tickets: TicketService
) -> None:
    other = await tickets.create(NewTicket(repository="sample", title="Another check"), by="owner")
    await _append_check(activity, ticket, START, "gate: old-step passed in 50s\n")
    for offset in range(1, 26):
        await _append_check(
            activity,
            other if offset % 2 else ticket,
            START + timedelta(seconds=offset),
            f"gate: pytest passed in {offset}s\n",
        )
    await _append_check(
        activity, other, START + timedelta(seconds=26), "gate: pytest passed in 100s\n", slept=True
    )

    entries = await _timings(client)
    assert [(row["step"], row["runs"], row["median"], row["slowest"]) for row in entries] == [
        ("pytest", 25, 13, 25)
    ]


async def test_failed_step_without_a_duration_still_counts_as_a_sample(
    client: httpx.AsyncClient, activity: ActivityService, ticket: Ticket
) -> None:
    log = "gate: pytest failed (exit 1)\n"
    data = checks_record(TARGET, 1, "checks.log", read_log(log), text=log)
    await activity.append(ticket.id, NewActivity(kind="checks", at=START, data=data), by="owner")

    [entry] = await _timings(client)

    assert (entry["step"], entry["runs"], entry["failed"], entry["median"]) == (
        "pytest",
        1,
        1,
        None,
    )
