"""The Flow page assembled from merges, tickets and runs, and the yields of the factory view."""

from datetime import UTC, datetime
from typing import Any

from code_factory.metrics.models import (
    Autonomy,
    ChecksVerdict,
    MergeFact,
    RunFacts,
    StageMove,
    TicketFlow,
)
from code_factory.metrics.rules.flow import InFlight, assemble_flow

NOW = 1_790_001_000.0
HOUR = 3600.0
DAY = 86400.0


def when(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


def ticket(
    ticket_id: str,
    created: float,
    *,
    caused_by: tuple[str, ...] = (),
    **fields: Any,  # noqa: ANN401
) -> TicketFlow:
    base: dict[str, Any] = {
        "id": ticket_id,
        "title": f"Idea {ticket_id}",
        "stage": "merged",
        "archived": False,
        "branch": "",
        "created_at": when(created),
        "caused_by": list(caused_by),
        "needs": "",
        "moves": [],
    }
    base.update(fields)
    return TicketFlow.model_validate(base)


def merge(
    number: int,
    at: float,
    *,
    ticket_id: str | None = None,
    started: float | None = None,
    autonomy: Autonomy = Autonomy.UNKNOWN,
) -> MergeFact:
    return MergeFact(
        repository="sample",
        commit=f"c{number}",
        head=f"h{number}",
        pull=number,
        branch=f"ticket/{ticket_id.lower()}" if ticket_id is not None else "other/branch",
        ticket=ticket_id,
        at=at,
        started=at - 10 if started is None else started,
        reverted=False,
        autonomy=autonomy,
        checks=ChecksVerdict.NONE,
    )


def run(
    ticket_id: str,
    started: float,
    *,
    stage: str = "build",
    cost: float | None = None,
    estimated: bool = False,
) -> RunFacts:
    return RunFacts(
        repository="sample",
        ticket_id=ticket_id,
        stage=stage,
        agent="",
        model="opus",
        connection="",
        started_at=when(started),
        exit_code=0,
        halted="",
        tokens=None,
        cost=cost,
        cost_estimated=estimated,
        commits=None,
    )


def page(
    merges: list[MergeFact],
    tickets: list[TicketFlow] | None = None,
    **given: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    arguments: dict[str, Any] = {
        "range_name": "7d",
        "now": NOW,
        "merges": merges,
        "tickets": {("sample", t.id): t for t in tickets or []},
        "runs": [],
        "build_starts": {},
        "in_flight": [],
        "web": {"sample": None},
    }
    arguments.update(given)
    return assemble_flow(**arguments)


def test_lead_runs_from_filing_when_the_ticket_is_known() -> None:
    result = page([merge(7, NOW - 760, ticket_id="CF-50")], [ticket("CF-50", NOW - 760 - 180)])
    [row] = result.merged
    assert (row.lead, row.from_, row.ticket, row.title, row.pull) == (
        180.0,
        "filed",
        "CF-50",
        "Idea CF-50",
        7,
    )


def test_lead_runs_from_the_first_commit_when_the_ticket_was_filed_after_the_merge() -> None:
    result = page([merge(7, 1000.0, ticket_id="CF-50", started=900.0)], [ticket("CF-50", 1001.0)])
    [row] = result.merged
    assert (row.lead, row.from_) == (100.0, "first_commit")
    assert result.lead.count == 0


def test_a_merge_of_no_known_ticket_has_an_empty_title_and_no_cost() -> None:
    [row] = page([merge(7, 1000.0, ticket_id="CF-9", started=900.0)]).merged
    assert (row.title, row.from_, row.cost, row.cost_estimated) == ("", "first_commit", None, None)


def test_a_lead_is_never_negative() -> None:
    [row] = page([merge(7, 1000.0, started=1500.0)]).merged
    assert row.lead == 0.0


def test_merges_are_listed_newest_first_and_a_merge_links_to_its_pull_request() -> None:
    result = page(
        [merge(1, 100.0), merge(2, 300.0), merge(3, 200.0)],
        web={"sample": "https://github.com/o/r"},
    )
    assert [(r.pull, r.url) for r in result.merged] == [
        (2, "https://github.com/o/r/pull/2"),
        (3, "https://github.com/o/r/pull/3"),
        (1, "https://github.com/o/r/pull/1"),
    ]


def test_a_merge_with_no_pull_number_or_no_web_address_has_no_url() -> None:
    no_pull = merge(1, 100.0).model_copy(update={"pull": None})
    result = page([no_pull, merge(2, 90.0)], web={"sample": "https://github.com/o/r"})
    assert [r.url for r in result.merged] == [None, "https://github.com/o/r/pull/2"]
    assert page([merge(2, 90.0)]).merged[0].url is None


def filed_merges(leads: list[int]) -> tuple[list[MergeFact], list[TicketFlow]]:
    merges: list[MergeFact] = []
    tickets: list[TicketFlow] = []
    for n, lead in enumerate(leads, start=1):
        merges.append(merge(n, 1_000_000.0 + n, ticket_id=f"CF-{n}"))
        tickets.append(ticket(f"CF-{n}", 1_000_000.0 + n - lead))
    return merges, tickets


def test_lead_statistics_are_nearest_rank_over_the_filed_merges() -> None:
    merges, tickets = filed_merges([10, 20, 30, 40, 50, 60, 70])
    result = page(merges, tickets)
    assert (result.lead.median, result.lead.p85, result.lead.p95, result.lead.count) == (
        40.0,
        60.0,
        70.0,
        7,
    )


def test_with_no_filed_merge_the_lead_statistics_are_none() -> None:
    assert page([]).lead.model_dump() == {"median": None, "p85": None, "p95": None, "count": 0}


def test_stuck_after_is_a_day_below_five_lead_samples() -> None:
    merges, tickets = filed_merges([10, 20, 30, 40])
    assert page(merges, tickets).stuck_after == DAY


def test_stuck_after_is_the_p85_with_five_samples_floored_at_an_hour() -> None:
    merges, tickets = filed_merges([10, 20, 30, 40, 50])
    assert page(merges, tickets).stuck_after == HOUR
    merges, tickets = filed_merges([10, 20, 30, 40, 100_000])
    assert page(merges, tickets).stuck_after == 100_000.0


def flight(ticket_id: str, cut: float | None, stage: str = "build") -> InFlight:
    return InFlight(
        repository="sample",
        ticket=ticket(
            ticket_id, 0.0, stage=stage, branch=f"ticket/{ticket_id.lower()}", needs="a review"
        ),
        cut=cut,
    )


def test_a_ticket_older_than_the_threshold_is_stuck_oldest_first_and_a_younger_one_is_not() -> None:
    result = page(
        [],
        in_flight=[
            flight("CF-1", NOW - DAY - 1),
            flight("CF-2", NOW - 2 * DAY),
            flight("CF-3", NOW - DAY),
            flight("CF-4", None),
        ],
    )
    assert result.in_flight == 4
    assert [(r.id, r.age) for r in result.stuck] == [("CF-2", 2 * DAY), ("CF-1", DAY + 1)]
    assert (result.stuck[0].repository, result.stuck[0].stage, result.stuck[0].needs) == (
        "sample",
        "build",
        "a review",
    )


def test_a_branch_cut_after_now_has_an_age_of_zero() -> None:
    assert page([], in_flight=[flight("CF-1", NOW + 50)]).stuck == []


def test_autonomy_counts_the_classes_and_the_share_of_the_classed() -> None:
    merges = [
        merge(1, 10.0, autonomy=Autonomy.AUTONOMOUS),
        merge(2, 20.0, autonomy=Autonomy.AUTONOMOUS),
        merge(3, 30.0, autonomy=Autonomy.AUTONOMOUS),
        merge(4, 40.0, autonomy=Autonomy.ASSISTED),
        merge(5, 50.0),
    ]
    result = page(merges).autonomy
    assert (result.autonomous, result.assisted, result.unknown, result.share) == (3, 1, 1, 0.75)


def test_the_autonomy_share_is_none_while_nothing_is_classed() -> None:
    assert page([merge(1, 10.0)]).autonomy.share is None


def test_cost_is_the_sum_of_a_tickets_runs_and_the_page_cost_their_median() -> None:
    merges = [
        merge(1, 100.0, ticket_id="CF-1"),
        merge(2, 200.0, ticket_id="CF-2"),
        merge(3, 300.0, ticket_id="CF-3"),
    ]
    tickets = [ticket("CF-1", 0.0), ticket("CF-2", 0.0), ticket("CF-3", 0.0)]
    runs = [
        run("CF-1", 10.0, cost=1.0),
        run("CF-1", 20.0, cost=2.0, estimated=True),
        run("CF-2", 30.0, cost=10.0),
        run("CF-3", 40.0),
    ]
    result = page(merges, tickets, runs=runs)
    by_ticket = {r.ticket: (r.cost, r.cost_estimated) for r in result.merged}
    assert by_ticket == {"CF-1": (3.0, True), "CF-2": (10.0, False), "CF-3": (None, None)}
    assert result.cost.model_dump() == {"median": 3.0, "estimated": True, "count": 2, "of": 3}


def test_a_run_of_another_repository_costs_the_ticket_nothing() -> None:
    other = run("CF-1", 10.0, cost=5.0).model_copy(update={"repository": "other"})
    [row] = page([merge(1, 100.0, ticket_id="CF-1")], [ticket("CF-1", 0.0)], runs=[other]).merged
    assert row.cost is None


def test_the_fixes_of_a_merge_are_the_tickets_that_name_it_as_their_cause() -> None:
    merges = [merge(1, 100.0, ticket_id="CF-1")]
    tickets = [
        ticket("CF-1", 0.0),
        ticket("CF-9", 0.0, caused_by=("CF-1",)),
        ticket("CF-4", 0.0, caused_by=("CF-1", "CF-2")),
        ticket("CF-5", 0.0, title="Fixes CF-1 in the text only"),
    ]
    assert page(merges, tickets).merged[0].fixes == ["CF-4", "CF-9"]


def test_completion_counts_a_build_start_once_and_not_after_now() -> None:
    merges = [
        merge(1, NOW - 100, ticket_id="CF-1"),
        merge(2, NOW - 50, ticket_id="CF-1"),
        merge(3, NOW - 200, ticket_id="CF-2"),
        merge(4, NOW + 100, ticket_id="CF-3"),
    ]
    starts = {"sample": {"CF-1": NOW - 500, "CF-2": NOW - 100, "CF-3": NOW - 90, "CF-4": NOW - 10}}
    result = page(merges, build_starts=starts)
    # CF-1 started before its merge, CF-2 after its merge, CF-3 merges after now, CF-4 never merged.
    assert (result.completion.started, result.completion.merged) == (4, 1)


def test_columns_are_the_median_minutes_over_the_merged_tickets() -> None:
    created = NOW - 5 * DAY
    moved = ticket(
        "CF-1",
        created,
        moves=[StageMove(at=when(created + 4320 * 60), to="build")],
    )
    result = page([merge(1, NOW - 100, ticket_id="CF-1")], [moved])
    assert result.columns.spec == 4320.0
    assert result.columns.build is not None
    assert result.columns.review is None


def test_the_range_and_its_window_are_echoed() -> None:
    result = page([], range_name="24h")
    assert (result.range, result.since, result.now) == ("24h", NOW - DAY, NOW)
    assert page([], range_name="bogus").range == "7d"


def test_the_wire_shape_leaves_cost_and_estimate_out_of_a_row_with_none() -> None:
    dumped = page([merge(7, 100.0)]).model_dump(mode="json")
    row = dumped["merged"][0]
    assert "cost" not in row
    assert "cost_estimated" not in row
    assert row["from"] == "first_commit"
    assert row["pull"] == 7


def test_a_page_with_nothing_is_zeros_and_nulls_not_an_error() -> None:
    empty = page([])
    assert empty.merged == []
    assert (empty.completion.started, empty.completion.merged, empty.in_flight) == (0, 0, 0)
    assert (empty.columns.spec, empty.cost.median, empty.cost.of) == (None, None, 0)
