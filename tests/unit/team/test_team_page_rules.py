"""The Team page's read from hand-written facts.

Expected values are the previous implementation's cases for the page: its groups and their order,
each kind of worker and wait, staleness, stage times against the cycle, the peek, one row per
ticket.
"""

import pytest

from code_factory.team.models import Row, TicketFacts, Worker
from code_factory.team.rules import assemble
from team_page_values import (
    DAY,
    HOUR,
    MINUTE,
    NOW,
    PULL,
    TODAY,
    activity,
    facts,
    ids,
    owner,
    ticket,
    worker,
)


def test_every_group_is_counted_and_an_idle_board_has_none() -> None:
    merged = ticket("CF-4", "merged", merged=NOW - HOUR)
    review = ticket(
        "CF-2",
        "review",
        pull=(f"{PULL}20", "open"),
        activities=(activity(NOW - 30 * MINUTE, "pull_request", url=f"{PULL}20"),),
    )
    team = assemble(
        facts(
            [ticket("CF-1", "spec"), review, ticket("CF-3", "build"), merged],
            [worker("CF-3", "agent", "builder", "build run", NOW - HOUR)],
            [owner("CF-1", "questions", "", NOW - 47 * MINUTE)],
        )
    )
    groups = team.groups
    assert (ids(groups.needs_you), ids(groups.waiting), ids(groups.working)) == (
        ["CF-1"],
        ["CF-2"],
        ["CF-3"],
    )
    assert ids(groups.done_today) == ["CF-4"]
    assert tuple(team.counts.model_dump().values()) == (1, 1, 1, 1, 0)
    assert tuple(assemble(facts()).counts.model_dump().values()) == (0, 0, 0, 0, 0)


def test_a_row_carries_who_what_and_since_and_a_done_row_is_frozen() -> None:
    merged = ticket(
        "CF-4",
        "merged",
        merged=NOW - HOUR,
        activities=(activity(NOW - 3 * HOUR, "created", type="bug"),),
    )
    team = assemble(
        facts(
            [ticket("CF-3", "build"), merged],
            [worker("CF-3", "agent", "builder", "build run", NOW - 70 * MINUTE)],
        )
    )
    working = team.groups.working[0]
    assert working.ticket is not None
    assert (working.state, working.ticket.title, working.actor.name, working.line) == (
        "working",
        "Title of CF-3",
        "builder",
        "build run",
    )
    assert (working.since, working.until) == (NOW - 70 * MINUTE, None)
    done = team.groups.done_today[0]
    assert (done.state, done.since, done.until) == ("merged", NOW - 3 * HOUR, NOW - HOUR)
    assert (done.actor.kind, done.actor.name) == ("board", "merged")


def test_a_merge_before_today_is_not_done_today() -> None:
    yesterday = ticket("CF-4", "merged", merged=TODAY - 1)
    today = ticket("CF-5", "merged", merged=TODAY)
    assert ids(assemble(facts([yesterday, today])).groups.done_today) == ["CF-5"]


def test_done_today_is_newest_first_and_counts_from_midnight() -> None:
    def merged(id_: str, at: float) -> TicketFacts:
        return ticket(id_, "merged", merged=at, activities=(activity(TODAY - HOUR, "created"),))

    team = assemble(facts([merged("CF-5", TODAY), merged("CF-6", TODAY + HOUR)]))
    assert ids(team.groups.done_today) == ["CF-6", "CF-5"]
    to_merge = next(s for s in team.stages if s.stage == "merged")
    assert (to_merge.today.median, to_merge.today.count) == (HOUR, 2)


def test_every_kind_of_worker_is_working_longest_first_and_an_agent_with_none_is_idle() -> None:
    team = assemble(
        facts(
            [ticket(id_, "build") for id_ in ("CF-3", "CF-4", "CF-5", "CF-6")],
            [
                worker("CF-4", "session", "ticket-worker 54f2", "Edit a.rs", NOW - 5 * MINUTE),
                worker("CF-3", "agent", "builder", "build run", NOW - HOUR),
                worker("CF-5", "board", "board land", "landing", NOW - MINUTE),
                worker(
                    "CF-6",
                    "gate",
                    "gate",
                    "rust-lint, holding the heavy-step lock",
                    NOW - 7 * MINUTE,
                ),
            ],
        )
    )
    assert ids(team.groups.working) == ["CF-3", "CF-6", "CF-4", "CF-5"]
    assert team.idle == ("writer",)


def test_a_paused_agent_is_named_paused_not_idle_and_one_still_working_is_neither() -> None:
    team = assemble(
        facts(
            [ticket("CF-3", "build")],
            [worker("CF-3", "agent", "builder", "build run", NOW - HOUR)],
            agents=("builder", "writer", "muse", "qwen"),
            paused=("builder", "muse", "qwen"),
        )
    )
    assert (team.idle, team.paused) == (("writer",), ("muse", "qwen"))


def test_waits_name_what_they_wait_on_oldest_first() -> None:
    pickup = ticket(
        "CF-7",
        "review",
        pull=(f"{PULL}20", "open"),
        activities=(activity(NOW - 30 * MINUTE, "pull_request", url=f"{PULL}20"),),
    )
    pushed = ticket("CF-8", "review", pushed_without_pull=True, column_since=NOW - 26 * MINUTE)
    conflict = ticket(
        "CF-9",
        "review",
        pull=(f"{PULL}21", "open"),
        activities=(
            activity(NOW - 50 * MINUTE, "pull_request", url=f"{PULL}21"),
            activity(NOW - 9 * MINUTE, "branch_conflict", default="abc"),
        ),
    )
    lock = worker(
        "CF-10",
        "gate",
        "gate",
        "waiting for the heavy-step lock behind CF-6 (rust-lint)",
        NOW - 4 * MINUTE,
        waiting=True,
    )
    team = assemble(facts([pickup, pushed, conflict, ticket("CF-10", "build")], [lock]))
    assert [
        (r.ticket.id if r.ticket else "", r.line, r.since, r.state) for r in team.groups.waiting
    ] == [
        ("CF-7", "waiting for a reviewer", NOW - 30 * MINUTE, "waiting"),
        ("CF-8", "branch pushed, no pull request yet", NOW - 26 * MINUTE, "waiting"),
        ("CF-9", "conflicts with main", NOW - 9 * MINUTE, "waiting"),
        (
            "CF-10",
            "waiting for the heavy-step lock behind CF-6 (rust-lint)",
            NOW - 4 * MINUTE,
            "waiting",
        ),
    ]
    assert [r.actor.name for r in team.groups.waiting[:3]] == [
        "reviewer",
        "board ship",
        "build agent",
    ]
    assert team.groups.working == ()


def test_work_in_hand_and_a_later_gate_pass_end_a_wait() -> None:
    reviewed = ticket("CF-7", "review", pull=(f"{PULL}20", "open"))
    resolved = ticket(
        "CF-9",
        "review",
        pull=(f"{PULL}21", "open"),
        activities=(
            activity(NOW - 9 * MINUTE, "branch_conflict", default="abc"),
            activity(NOW - 2 * MINUTE, "checks", exit_code=0, commit="def"),
        ),
    )
    team = assemble(
        facts(
            [reviewed, resolved],
            [worker("CF-7", "reviewer", "reviewer", "reviewing #20", NOW - MINUTE)],
        )
    )
    assert ids(team.groups.waiting) == ["CF-9"]
    assert team.groups.waiting[0].line == "waiting for a reviewer"
    assert ids(team.groups.working) == ["CF-7"]


def test_needs_you_holds_decisions_and_stale_work_oldest_first() -> None:
    quiet = worker(
        "CF-12",
        "session",
        "ticket-worker 7c2e",
        "Bash cargo test",
        NOW - HOUR,
        last_event=NOW - 601,
    )
    gone = worker(
        "CF-11",
        "board",
        "board land",
        "landing",
        NOW - 3 * DAY,
        alive=False,
        last_event=NOW - 30 * MINUTE,
    )
    fresh = worker(
        "CF-13", "session", "ticket-worker 1111", "Read b.rs", NOW - 2 * HOUR, last_event=NOW - 600
    )
    gate = worker(
        "CF-14", "gate", "gate", "rust-test", NOW - HOUR, last_event=NOW - 1500, stale_after=2000.0
    )
    team = assemble(
        facts(
            [ticket(f"CF-{n}", "build") for n in range(10, 15)],
            [quiet, gone, fresh, gate],
            [owner("CF-10", "screens", "", NOW - 47 * MINUTE)],
        )
    )
    assert [(r.state, r.since) for r in team.groups.needs_you] == [("owner", NOW - 47 * MINUTE)]
    assert [(r.ticket.id if r.ticket else "", r.state, r.since) for r in team.groups.stale] == [
        ("CF-11", "stale", NOW - 30 * MINUTE),
        ("CF-12", "stale", NOW - 601),
    ]
    assert ids(team.groups.working) == ["CF-13", "CF-14"]
    assert team.groups.stale[0].line == "landing; its process has ended"
    assert team.groups.stale[1].line == "Bash cargo test; no event since"


def test_stale_rows_have_their_own_group_below_all_live_work() -> None:
    gone = worker(
        "CF-11",
        "board",
        "board land",
        "landing",
        NOW - 3 * DAY,
        alive=False,
        last_event=NOW - 30 * MINUTE,
    )
    quiet = worker(
        "CF-12",
        "session",
        "ticket-worker 7c2e",
        "Read a.rs",
        NOW - HOUR,
        last_event=NOW - 20 * MINUTE,
    )
    queued = worker(
        "CF-17", "gate", "gate", "rust-test", NOW - HOUR, waiting=True, last_event=NOW - 40 * MINUTE
    )
    team = assemble(
        facts(
            [ticket(f"CF-{n}", "build") for n in (10, 11, 12, 15, 16, 17, 18)],
            [gone, quiet, queued, worker("CF-18", "agent", "builder", "build run", NOW - HOUR)],
            [
                owner("CF-10", "screens", "", NOW - 47 * MINUTE),
                owner("CF-15", "stopped", "stopped at its cap", NOW - 2 * HOUR),
                owner("CF-16", "spec", "", NOW - 5 * MINUTE),
            ],
        )
    )
    assert ids(team.groups.needs_you) == ["CF-10", "CF-16"]
    assert ids(team.groups.working) == ["CF-18"]
    assert all(row.state != "stale" for row in team.groups.waiting)
    assert ids(team.groups.stale) == ["CF-15", "CF-17", "CF-11", "CF-12"]
    assert (team.counts.needs_you, team.counts.working, team.counts.stale) == (2, 1, 4)


def test_a_session_or_run_quiet_for_an_hour_leaves_the_page_and_a_live_job_stays_stale() -> None:
    def quiet(id_: str, kind: str, minutes: float, *, alive: bool = True) -> Worker:
        return worker(
            id_,
            kind,
            "w",
            "Read a.rs",
            NOW - 2 * HOUR,
            last_event=NOW - minutes * MINUTE,
            alive=alive,
        )

    workers = [
        quiet("CF-1", "session", 59.5),
        quiet("CF-2", "session", 60),
        quiet("CF-3", "agent", 59),
        quiet("CF-4", "reviewer", 60),
        quiet("CF-5", "agent", 60, alive=False),
        quiet("CF-6", "board", 95),
        quiet("CF-7", "gate", 90),
    ]
    team = assemble(facts([ticket(f"CF-{n}", "build") for n in range(1, 8)], workers))
    shown = [
        *ids(team.groups.needs_you),
        *ids(team.groups.waiting),
        *ids(team.groups.working),
        *ids(team.groups.stale),
    ]
    assert shown == ["CF-6", "CF-7", "CF-1", "CF-3"]
    assert team.counts.stale == 4


def test_a_job_whose_process_ended_an_hour_ago_leaves_the_page() -> None:
    def job(id_: str, kind: str, minutes: float, *, alive: bool) -> Worker:
        return worker(
            id_,
            kind,
            "w",
            "landing",
            NOW - 2 * HOUR,
            last_event=NOW - minutes * MINUTE,
            alive=alive,
        )

    workers = [
        job("CF-1", "board", 60, alive=False),
        job("CF-2", "gate", 59, alive=False),
        job("CF-3", "board", 300, alive=True),
        job("CF-4", "gate", 120, alive=False),
    ]
    team = assemble(facts([ticket(f"CF-{n}", "build") for n in range(1, 5)], workers))
    assert ids(team.groups.stale) == ["CF-3", "CF-2"]
    assert team.counts.stale == 2


def test_an_owner_item_says_what_it_waits_for() -> None:
    team = assemble(
        facts(
            owners=[
                owner("CF-1", "questions", "", NOW - HOUR, count=2),
                owner("CF-2", "questions", "", NOW - 50 * MINUTE),
                owner("CF-3", "screens", "", NOW - 40 * MINUTE),
                owner("CF-5", "stopped", "stopped at its cap", NOW - 20 * MINUTE),
                owner("CF-6", "stopped", "", NOW - 10 * MINUTE),
                owner("CF-7", "spec", "", NOW - 9 * MINUTE),
                owner("CF-8", "spec", "needs a decision", NOW - 8 * MINUTE),
            ]
        )
    )
    assert [(r.state, r.line) for r in team.groups.needs_you] == [
        ("owner", "2 open questions"),
        ("owner", "1 open question"),
        ("owner", "screens wait for your approval"),
        ("owner", "spec"),
        ("owner", "needs a decision"),
    ]
    first = team.groups.needs_you[0].ticket
    assert first is not None
    assert first.title == "Title of CF-1"
    assert [(r.state, r.line) for r in team.groups.stale] == [
        ("stale", "stopped at its cap"),
        ("stale", "stopped"),
    ]


def test_stage_times_read_today_against_the_cycle() -> None:
    def filed(id_: str, at: float, merged: float) -> TicketFacts:
        return ticket(id_, "merged", merged=merged, activities=(activity(at, "created"),))

    team = assemble(
        facts(
            [
                filed("CF-1", NOW - 2 * HOUR, NOW - HOUR),
                filed("CF-2", NOW - 4 * HOUR, NOW - HOUR),
                filed("CF-3", NOW - 3 * DAY, NOW - 3 * DAY + 2 * HOUR),
                filed("CF-4", NOW - 9 * DAY, NOW - 8 * DAY),
            ]
        )
    )
    by_stage = {s.stage: s for s in team.stages}
    assert (by_stage["merged"].today.median, by_stage["merged"].today.count) == (HOUR, 2)
    assert (by_stage["merged"].cycle.median, by_stage["merged"].cycle.count) == (2 * HOUR, 3)
    assert (by_stage["pull_request"].today.median, by_stage["pull_request"].today.count) == (
        None,
        0,
    )
    assert [s.stage for s in team.stages] == ["first_commit", "pull_request", "gate_pass", "merged"]


@pytest.mark.parametrize(
    ("values", "expected"),
    [([10, 20, 30, 40], 20), ([5], 5), ([40, 10, 30, 20, 50], 30), ([], None)],
)
def test_a_median_is_the_nearest_rank_of_the_sorted_seconds(
    values: list[float], expected: float | None
) -> None:
    tickets = [
        ticket(
            f"CF-{n}",
            "merged",
            merged=TODAY + 1000 + seconds,
            activities=(activity(TODAY + 1000, "created"),),
        )
        for n, seconds in enumerate(values, start=1)
    ]
    merged = next(s for s in assemble(facts(tickets)).stages if s.stage == "merged")
    assert (merged.today.median, merged.today.count) == (expected, len(values))


def test_the_peek_holds_milestones_and_the_last_five_events_newest_first() -> None:
    checks = [
        activity(NOW - minutes * MINUTE, "checks", exit_code=1, commit=name)
        for minutes, name in ((90, "aaa"), (80, "bbb"), (70, "ccc"), (60, "ddd"))
    ]
    open_ticket = ticket(
        "CF-7",
        "review",
        first_commit=NOW - 100 * MINUTE,
        pull=(f"{PULL}20", "open"),
        activities=(
            activity(NOW - 2 * HOUR, "created", type="bug"),
            *checks,
            activity(
                NOW - 30 * MINUTE,
                "pull_request",
                url=f"{PULL}20",
                words=f"Pull request opened ({PULL}20)",
            ),
        ),
    )
    done = ticket(
        "CF-1",
        "merged",
        first_commit=NOW - 4 * HOUR,
        merged=NOW - 2 * HOUR,
        activities=(activity(NOW - 5 * HOUR, "created"),),
    )
    peek = assemble(facts([open_ticket, done])).peek["sample/CF-7"]
    assert [(m.stage, m.at, m.cycle) for m in peek.milestones] == [
        ("filed", NOW - 2 * HOUR, None),
        ("first_commit", NOW - 100 * MINUTE, 20 * MINUTE),
        ("pull_request", NOW - 30 * MINUTE, 90 * MINUTE),
        ("gate_pass", None, None),
        ("merged", None, 3 * HOUR),
    ]
    assert [e.at for e in peek.events] == [
        NOW - 30 * MINUTE,
        NOW - 60 * MINUTE,
        NOW - 70 * MINUTE,
        NOW - 80 * MINUTE,
        NOW - 90 * MINUTE,
    ]
    assert peek.events[0].words == f"Pull request opened ({PULL}20)"
    assert (peek.kind, peek.column) == ("feature", "review")


def test_a_row_shows_its_pull_request_state() -> None:
    def pull(id_: str, number: int, state: str, checks: int | None) -> TicketFacts:
        url = f"{PULL}{number}"
        records = (activity(NOW - HOUR, "pull_request", url=url),)
        check = None if checks is None else checks == 0
        return ticket(id_, "review", pull=(url, state), activities=records, check=check)

    conflicted = pull("CF-4", 23, "open", None)
    conflicted = conflicted.model_copy(
        update={
            "activities": (
                *conflicted.activities,
                activity(NOW - 10 * MINUTE, "branch_conflict", default="abc"),
            )
        }
    )
    gated = worker("CF-3", "gate", "gate", "rust-test", NOW - MINUTE, key="gate:CF-3")
    team = assemble(
        facts(
            [
                pull("CF-1", 20, "open", None),
                pull("CF-2", 21, "open", 1),
                pull("CF-3", 22, "open", 0),
                conflicted,
            ],
            [gated],
        )
    )
    rows: list[Row] = [*team.groups.waiting, *team.groups.working]
    assert [
        (r.ticket.id if r.ticket else "", r.pull.number, r.pull.gate, r.pull.merge)
        for r in rows
        if r.pull
    ] == [
        ("CF-1", 20, "not_run", "open"),
        ("CF-2", 21, "failed", "open"),
        ("CF-4", 23, "not_run", "conflict"),
        ("CF-3", 22, "running", "open"),
    ]


def test_a_row_gate_is_the_checks_verdict_on_the_head_the_ticket_page_shows() -> None:
    # The checks module judged the head though no `checks` activity was written: the row reads the
    # same verdict as the ticket page, not "checks not run".
    def review(id_: str, number: int, **fields: bool) -> TicketFacts:
        url = f"{PULL}{number}"
        opened = (activity(NOW - HOUR, "pull_request", url=url),)
        return ticket(id_, "review", pull=(url, "open"), activities=opened, **fields)

    team = assemble(
        facts([review("CF-1", 30, check=True), review("CF-2", 31, check=False), review("CF-3", 32)])
    )
    gates = {r.ticket.id: r.pull.gate for r in team.groups.waiting if r.ticket and r.pull}
    assert gates == {"CF-1": "passed", "CF-2": "failed", "CF-3": "not_run"}


def test_a_merged_pull_request_is_merged_and_a_closed_one_shows_none() -> None:
    merged = ticket("CF-1", "build", pull=(f"{PULL}5", "merged"))
    closed = ticket("CF-2", "build", pull=(f"{PULL}6", "closed"))
    team = assemble(
        facts(
            [merged, closed],
            [
                worker("CF-1", "agent", "builder", "x", NOW),
                worker("CF-2", "agent", "builder", "x", NOW, key="other"),
            ],
        )
    )
    assert [(r.pull.merge if r.pull else None) for r in team.groups.working] == ["merged", None]
