"""One row per ticket on the Team page, the conflict words, when a pull request opened, and the
board's ship; expected values are the previous implementation's cases."""

from typing import Any

import pytest

from code_factory.team.models import Row, TicketFacts
from code_factory.team.rules import assemble, ship_worker
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


def told(rows: tuple[Row, ...]) -> list[tuple[str, str, list[tuple[str, str, str, float]]]]:
    """Each row as its ticket, its line and its second lines."""
    return [
        (
            r.ticket.id if r.ticket else "",
            r.line,
            [(a.state, a.actor.name, a.line, a.since) for a in r.also],
        )
        for r in rows
    ]


def test_a_ticket_in_two_groups_is_one_row_in_the_most_urgent() -> None:
    team = assemble(
        facts(
            [ticket("CF-1", "build")],
            owners=[
                owner("CF-1", "stopped", "agent failed", NOW - 50 * DAY),
                owner("CF-1", "questions", "", NOW - HOUR, count=3),
            ],
        )
    )
    assert told(team.groups.needs_you) == [
        ("CF-1", "3 open questions", [("stale", "you", "agent failed", NOW - 50 * DAY)])
    ]
    assert team.groups.needs_you[0].since == NOW - HOUR
    assert told(team.groups.stale) == []
    assert (team.counts.needs_you, team.counts.stale) == (1, 0)
    assert list(team.peek) == ["sample/CF-1"]


def test_the_most_urgent_state_of_a_ticket_keeps_its_row() -> None:
    gone = worker(
        "CF-2",
        "board",
        "board land",
        "landing",
        NOW - HOUR,
        alive=False,
        last_event=NOW - 20 * MINUTE,
    )
    held = worker("CF-2", "gate", "gate", "waits for the lock", NOW - 5 * MINUTE, waiting=True)
    landed = ticket(
        "CF-3", "merged", merged=TODAY + HOUR, activities=(activity(TODAY - HOUR, "created"),)
    )
    team = assemble(
        facts(
            [ticket("CF-2", "build"), landed, ticket("CF-4", "build")],
            [
                gone,
                held,
                worker("CF-2", "agent", "builder", "build run", NOW - 9 * MINUTE),
                worker("CF-3", "session", "ticket-worker 1111", "Read a.rs", NOW - MINUTE),
                worker("CF-4", "gate", "gate", "rust-test", NOW - 2 * MINUTE),
                worker("CF-4", "agent", "builder", "build run", NOW - 8 * MINUTE),
            ],
        )
    )
    assert told(team.groups.stale) == [
        (
            "CF-2",
            "landing; its process has ended",
            [
                ("waiting", "gate", "waits for the lock", NOW - 5 * MINUTE),
                ("working", "builder", "build run", NOW - 9 * MINUTE),
            ],
        )
    ]
    assert told(team.groups.waiting) == []
    assert told(team.groups.working) == [
        ("CF-4", "build run", [("working", "gate", "rust-test", NOW - 2 * MINUTE)]),
        ("CF-3", "Read a.rs", [("merged", "merged", "", TODAY - HOUR)]),
    ]
    assert team.groups.working[1].also[0].until == TODAY + HOUR
    assert told(team.groups.done_today) == []
    assert (
        team.counts.stale,
        team.counts.waiting,
        team.counts.working,
        team.counts.done_today,
    ) == (1, 0, 2, 0)


def test_rows_of_different_tickets_or_of_none_stay_apart() -> None:
    elsewhere = worker(
        "CF-5",
        "agent",
        "builder",
        "build run",
        NOW - 3 * MINUTE,
        repository="other",
        key="b:other/CF-5",
    )
    loose = worker("CF-0", "session", "explorer aaaa", "Read a.rs", NOW - 2 * MINUTE, ticket=None)
    free = worker(
        "CF-0", "session", "explorer bbbb", "Read b.rs", NOW - MINUTE, ticket=None, key="s:bbbb"
    )
    team = assemble(
        facts(
            [ticket("CF-5", "build"), ticket("CF-6", "build")],
            [
                worker("CF-5", "agent", "builder", "build run", NOW - 5 * MINUTE),
                worker("CF-6", "agent", "builder", "build run", NOW - 4 * MINUTE),
                elsewhere,
                loose,
                free,
            ],
        )
    )
    assert told(team.groups.working) == [
        ("CF-5", "build run", []),
        ("CF-6", "build run", []),
        ("CF-5", "build run", []),
        ("", "Read a.rs", []),
        ("", "Read b.rs", []),
    ]
    assert team.counts.working == 5


def conflict(id_: str, **data: Any) -> TicketFacts:  # noqa: ANN401
    """A ticket in Review with a conflict record holding `data`."""
    return ticket(
        id_,
        "review",
        activities=(activity(NOW - 9 * MINUTE, "branch_conflict", default="abc", **data),),
    )


@pytest.mark.parametrize(
    ("data", "line"),
    [
        ({}, "conflicts with main"),
        ({"files": ""}, "conflicts with main"),
        ({"files": "src/a.rs"}, "conflicts with main in src/a.rs"),
        ({"files": "a.rs, b.rs, c.rs"}, "conflicts with main in a.rs, b.rs, c.rs"),
        (
            {"files": "a.rs, b.rs, c.rs, d.rs, e.rs"},
            "conflicts with main in a.rs, b.rs, c.rs and 2 more",
        ),
    ],
)
def test_a_conflict_row_names_the_first_three_conflicting_files_and_the_count_of_the_rest(
    data: dict[str, str], line: str
) -> None:
    team = assemble(facts([conflict("CF-1", **data)]))
    assert [r.line for r in team.groups.waiting] == [line]


def recorded_pulls(*records: tuple[float, int, bool]) -> TicketFacts:
    """CF-7 in Review filed 5 hours ago, with `pull_request` records (minutes ago, number, head)."""
    acts = [activity(NOW - 5 * HOUR, "created")]
    for minutes, number, head in records:
        data = {"url": f"{PULL}{number}", **({"head": "abc"} if head else {})}
        acts.append(activity(NOW - minutes * MINUTE, "pull_request", **data))
    last = records[-1][1]
    return ticket("CF-7", "review", pull=(f"{PULL}{last}", "open"), activities=tuple(acts))


def opened_at(candidate: TicketFacts) -> tuple[float | None, tuple[float | None, int], float]:
    """CF-7's pull request milestone, its stage's median today with count, and its row's since."""
    team = assemble(facts([candidate]))
    at = next(m.at for m in team.peek["sample/CF-7"].milestones if m.stage == "pull_request")
    stage = next(s for s in team.stages if s.stage == "pull_request")
    return at, (stage.today.median, stage.today.count), team.groups.waiting[0].since


def test_a_pull_request_recorded_twice_opened_at_its_first_record() -> None:
    twice = recorded_pulls((240, 20, False), (64, 20, True))
    assert opened_at(twice) == (NOW - 4 * HOUR, (HOUR, 1), NOW - 4 * HOUR)


def test_a_second_pull_request_opened_at_its_own_first_record() -> None:
    replaced = recorded_pulls((240, 20, True), (120, 21, False), (60, 21, True))
    assert opened_at(replaced) == (NOW - 2 * HOUR, (3 * HOUR, 1), NOW - 2 * HOUR)


def test_a_pull_request_recorded_once_opened_at_that_record() -> None:
    assert opened_at(recorded_pulls((30, 20, True))) == (
        NOW - 30 * MINUTE,
        (4.5 * HOUR, 1),
        NOW - 30 * MINUTE,
    )


def shipping(column: str, *kinds: tuple[str, float]) -> TicketFacts:
    """CF-7 in `column` with records `(kind, seconds before now)`, oldest first."""
    records = tuple(activity(NOW - ago, kind, head="abc") for kind, ago in kinds)
    return ticket("CF-7", column, activities=records)


def page(candidate: TicketFacts) -> Any:  # noqa: ANN401
    """The page as the gather builds it: the ticket and its ship, when one shows."""
    ship = ship_worker(candidate, NOW)
    return assemble(facts([candidate], [ship] if ship else []))


def shown(rows: tuple[Row, ...]) -> list[tuple[str, str, str, str, float]]:
    return [(r.state, r.actor.kind, r.actor.name, r.line, r.since) for r in rows]


def test_a_ship_that_started_and_has_not_ended_is_a_working_row() -> None:
    team = page(shipping("build", ("ship_started", 2 * MINUTE)))
    assert shown(team.groups.working) == [
        ("working", "board", "board ship", "pushing the branch", NOW - 2 * MINUTE)
    ]
    assert team.groups.working[0].key == "ship:sample/CF-7"
    assert team.counts.stale == 0


def test_a_ship_that_pushed_says_it_opens_the_pull_request() -> None:
    team = page(shipping("build", ("ship_started", 2 * MINUTE), ("ship_pushed", MINUTE)))
    assert shown(team.groups.working) == [
        (
            "working",
            "board",
            "board ship",
            "branch pushed, opening its pull request",
            NOW - 2 * MINUTE,
        )
    ]


@pytest.mark.parametrize("end", ["pull_request", "branch_pushed", "ship_failed"])
def test_a_pull_request_a_later_push_or_a_failure_ends_a_ship(end: str) -> None:
    team = page(shipping("build", ("ship_started", 2 * MINUTE), ("ship_pushed", 90), (end, MINUTE)))
    assert (shown(team.groups.working), shown(team.groups.stale)) == ([], [])


def test_a_ship_started_again_after_a_failure_is_working() -> None:
    team = page(
        shipping(
            "build",
            ("ship_started", 30 * MINUTE),
            ("ship_failed", 29 * MINUTE),
            ("ship_started", MINUTE),
        )
    )
    assert [r.since for r in team.groups.working] == [NOW - MINUTE]


def test_a_start_with_no_end_is_working_for_600_seconds_then_stale() -> None:
    at_bound = page(shipping("build", ("ship_started", 600)))
    past_bound = page(shipping("build", ("ship_started", 601)))
    assert (at_bound.counts.working, at_bound.counts.stale) == (1, 0)
    assert past_bound.counts.working == 0
    assert shown(past_bound.groups.stale) == [
        ("stale", "board", "board ship", "pushing the branch; no event since", NOW - 601)
    ]


def test_a_start_with_no_end_for_an_hour_is_on_no_row() -> None:
    assert page(shipping("build", ("ship_started", 3599))).counts.stale == 1
    gone = page(shipping("build", ("ship_started", 3600)))
    assert (gone.counts.stale, gone.counts.working) == (0, 0)


def test_a_pushed_branch_with_no_pull_request_waits_since_its_push() -> None:
    pushed = shipping(
        "review",
        ("ship_started", 9 * MINUTE),
        ("ship_pushed", 8 * MINUTE),
        ("ship_failed", 7 * MINUTE),
    ).model_copy(update={"pushed_without_pull": True, "column_since": NOW - 26 * MINUTE})
    assert shown(page(pushed).groups.waiting) == [
        ("waiting", "board", "board ship", "branch pushed, no pull request yet", NOW - 8 * MINUTE)
    ]


def test_a_ship_on_a_ticket_that_needs_the_owner_is_that_rows_second_line() -> None:
    candidate = shipping("build", ("ship_started", 2 * MINUTE))
    ship = ship_worker(candidate, NOW)
    assert ship is not None
    question = owner("CF-7", "questions", "", NOW - 30 * MINUTE)
    team = assemble(facts([candidate], [ship], [question]))
    assert (team.counts.needs_you, team.counts.working) == (1, 0)
    assert [(a.state, a.actor.name, a.line, a.since) for a in team.groups.needs_you[0].also] == [
        ("working", "board ship", "pushing the branch", NOW - 2 * MINUTE)
    ]


def test_a_ship_worker_is_stale_after_600_seconds_by_its_own_threshold() -> None:
    ship = ship_worker(shipping("build", ("ship_started", 100)), NOW)
    assert ship is not None
    assert (ship.stale_after, ship.alive, ship.last_event, ship.waiting) == (
        600.0,
        True,
        NOW - 100,
        False,
    )
    assert ids(page(shipping("build")).groups.working) == []


def test_owner_rows_and_rows_of_one_age_are_ordered_oldest_first_then_by_key() -> None:
    team = assemble(
        facts(
            owners=[
                owner("CF-2", "screens", "", NOW - 10 * MINUTE),
                owner("CF-1", "screens", "", NOW - HOUR),
                owner("CF-4", "questions", "", NOW - 5 * MINUTE),
                owner("CF-3", "questions", "", NOW - 5 * MINUTE),
            ]
        )
    )
    assert ids(team.groups.needs_you) == ["CF-1", "CF-2", "CF-3", "CF-4"]


def test_an_owner_item_on_a_ticket_keeps_it_from_waiting_for_review_pickup() -> None:
    reviewed = ticket("CF-1", "review", pull=(f"{PULL}3", "open"))
    team = assemble(facts([reviewed], owners=[owner("CF-1", "questions", "", NOW - HOUR)]))
    assert (ids(team.groups.waiting), ids(team.groups.needs_you)) == ([], ["CF-1"])
    assert team.groups.needs_you[0].also == ()


def test_a_worker_gone_for_good_no_longer_keeps_a_ticket_from_waiting() -> None:
    reviewed = ticket("CF-1", "review", pull=(f"{PULL}3", "open"))
    gone = worker(
        "CF-1", "reviewer", "reviewer", "reviewing", NOW - 3 * HOUR, last_event=NOW - HOUR
    )
    assert ids(assemble(facts([reviewed], [gone])).groups.waiting) == ["CF-1"]


def test_a_conflict_is_ended_by_a_later_pull_request_record_but_not_one_at_the_same_second() -> (
    None
):
    def conflicted(*later: tuple[str, float]) -> TicketFacts:
        records = [activity(NOW - 9 * MINUTE, "branch_conflict", default="abc")]
        records += [activity(NOW - ago, kind, url=f"{PULL}3") for kind, ago in later]
        return ticket("CF-1", "review", pull=(f"{PULL}3", "open"), activities=tuple(records))

    lines = {
        "later pull": assemble(facts([conflicted(("pull_request", 2 * MINUTE))])),
        "same second": assemble(facts([conflicted(("checks", 9 * MINUTE))])),
        "later checks": assemble(facts([conflicted(("checks", MINUTE))])),
    }
    assert lines["later pull"].groups.waiting[0].line == "waiting for a reviewer"
    assert lines["same second"].groups.waiting[0].line == "conflicts with main"
    assert lines["later checks"].groups.waiting[0].line == "waiting for a reviewer"


def test_a_stage_reached_before_the_filing_counts_no_time() -> None:
    odd = ticket(
        "CF-1",
        "merged",
        merged=TODAY + 10,
        activities=(activity(TODAY + 100, "created"),),
    )
    merged = next(s for s in assemble(facts([odd])).stages if s.stage == "merged")
    assert (merged.today.median, merged.today.count) == (None, 0)


def test_an_agent_with_a_live_review_run_is_neither_idle_nor_paused() -> None:
    reviewing = worker("CF-1", "reviewer", "writer", "review run", NOW - MINUTE)
    stale_review = worker(
        "CF-2", "reviewer", "muse", "review run", NOW - HOUR, last_event=NOW - 20 * MINUTE
    )
    team = assemble(
        facts(
            [ticket("CF-1", "review"), ticket("CF-2", "review")],
            [reviewing, stale_review],
            agents=("writer", "muse", "idler"),
            paused=("muse",),
        )
    )
    assert (team.idle, team.paused) == (("idler",), ("muse",))
