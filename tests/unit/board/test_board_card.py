"""A card built from a ticket's facts equals the card the app was specified against."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_factory.board.models import (
    CardFacts,
    Placement,
    PullFacts,
    RunCard,
    RunCost,
    SessionFacts,
    TicketRuns,
)
from code_factory.board.rules.card import build_card, card_pull
from code_factory.board.rules.parts import session_chips
from code_factory.tickets.models import Ticket

GOLDEN = json.loads(
    (Path(__file__).parents[2] / "support/golden/formats/api/board.golden.json").read_text()
)
TODAY = datetime(2026, 9, 21, 10, tzinfo=UTC)
LONG = "A description long enough to be cut. " * 12


def golden_card(ticket_id: str) -> dict[str, Any]:
    cards = [c for column in GOLDEN["columns"].values() for c in column]
    return next(c for c in cards if c["id"] == ticket_id)


def ticket(**fields: Any) -> Ticket:  # noqa: ANN401
    base: dict[str, Any] = {
        "id": "CF-2",
        "number": 2,
        "repository": "sample",
        "title": "A bug in flight",
        "type": "bug",
        "description": LONG,
        "labels": ["ui", "agents"],
        "priority": "high",
        "assignee": "alex",
        "due": "2026-10-10",
        "blocked": "waiting on design",
        "rank": 1,
        "e2e": "",
        "tests": "",
        "budget": "2.5",
        "parallel": "",
        "source": "",
        "steps": "",
        "pages": "",
        "parent": "CF-1",
        "blocked_by": [],
        "caused_by": [],
        "archived": False,
        "branch": "feat/CF-2",
        "pull_request": None,
        "merged": False,
        "column": "build",
        "created_at": TODAY,
        "updated_at": TODAY,
    }
    return Ticket(**(base | fields))


def in_flight() -> CardFacts:
    return CardFacts(
        ticket=ticket(),
        placement=Placement(
            stage="build",
            evidence_stage="build",
            hold={
                "stage": "build",
                "detail": "a commit on feat/CF-2",
                "summary": "a commit on feat/CF-2",
            },
        ),
        stage_since="2026-10-01T09:00:00Z",
        repository_path="{root}",
        pull=PullFacts(
            state="open",
            review="approved",
            ci="failed",
            head="1234567abcdef",
            url="https://github.com/o/r/pull/2",
            at="1790000000.0",
        ),
        check={"passed": True, "commit": "1234567abcdef"},
        runs=TicketRuns(
            runs=[
                RunCard(
                    id="aaaaaaaaaaaa",
                    stage="build",
                    iteration=2,
                    loop=True,
                    max_iterations=8,
                    attempt=0,
                    agent="",
                    started_at=1790000500.0,
                )
            ],
            spent=4.25,
        ),
        sessions=session_chips(
            [
                SessionFacts(
                    session_id="s-rest",
                    cwd="/x/.code-factory/worktrees/CF-2",
                    branch="",
                    state="idle",
                )
            ],
            "CF-2",
            "feat/CF-2",
            "main",
        ),
    )


def test_the_card_of_a_ticket_in_flight_equals_the_golden_card() -> None:
    card = build_card(in_flight(), TODAY)
    assert card == golden_card("CF-2")
    assert list(card) == list(golden_card("CF-2"))


def test_a_ticket_with_no_runs_spends_the_integer_zero() -> None:
    facts = CardFacts(ticket=ticket(), placement=Placement(stage="build", evidence_stage="build"))
    spent = build_card(facts, TODAY)["spent"]
    assert (spent, type(spent)) == (0, int)


def test_spent_is_a_float_once_a_run_reports() -> None:
    facts = in_flight().model_copy(update={"runs": TicketRuns(spent=0.5)})
    spent = build_card(facts, TODAY)["spent"]
    assert (spent, type(spent)) == (0.5, float)


def test_the_ticket_budget_wins_over_the_repository_budget() -> None:
    facts = in_flight().model_copy(update={"repository_budget": 5.0})
    assert build_card(facts, TODAY)["budget"] == 2.5


def test_the_repository_budget_stands_in_for_an_empty_ticket_budget() -> None:
    facts = CardFacts(
        ticket=ticket(budget=""),
        placement=Placement(stage="build", evidence_stage="build"),
        repository_budget=5.0,
    )
    assert build_card(facts, TODAY)["budget"] == 5.0


def test_an_unset_optional_key_is_absent_from_the_card() -> None:
    plain = build_card(in_flight(), TODAY)
    assert {
        "spent_estimated",
        "delivery_event",
        "checks_configured",
        "queue",
        "overlap",
        "holder",
    } & set(plain) == set()


def test_a_set_optional_key_is_present_after_the_fixed_ones() -> None:
    facts = in_flight().model_copy(
        update={
            "runs": TicketRuns(spent=1.0, spent_estimated=True),
            "delivery_event": {"kind": "pull_request", "at": 1.0, "retry_at": None},
            "checks_configured": True,
            "queue": {"queue": "next", "overlap": "CF-9", "holder": "claude"},
        }
    )
    card = build_card(facts, TODAY)
    assert list(card)[-6:] == [
        "spent_estimated",
        "delivery_event",
        "checks_configured",
        "queue",
        "overlap",
        "holder",
    ]
    assert card["spent_estimated"] is True


def test_a_merged_ticket_has_no_hold_and_is_never_due() -> None:
    facts = CardFacts(
        ticket=ticket(due="2026-09-01"),
        placement=Placement(
            stage="merged",
            evidence_stage="merged",
            hold={"stage": "merged", "detail": "main", "summary": "main"},
        ),
    )
    card = build_card(facts, TODAY)
    assert (card["hold"], card["due_state"]) == (None, "")


def test_the_cards_cost_words_come_from_the_runs() -> None:
    facts = in_flight().model_copy(
        update={
            "runs": TicketRuns(
                spent=1.0,
                halted="agent failed (exit 1)",
                limited_until=1790000000.0,
                cost=RunCost(),
            )
        }
    )
    card = build_card(facts, TODAY)
    assert (card["halted"], card["limited_until"]) == ("agent failed (exit 1)", 1790000000.0)


def test_the_checklist_counts_come_from_the_whole_description() -> None:
    text = "- [x] one\n- [ ] two\n" + "x" * 400
    facts = CardFacts(
        ticket=ticket(description=text), placement=Placement(stage="spec", evidence_stage="spec")
    )
    card = build_card(facts, TODAY)
    assert (card["checklist"], len(card["description"])) == ([1, 2], 280)


def test_the_card_shows_the_pull_requests_size_when_it_is_known() -> None:
    sized = card_pull(
        PullFacts(state="open", head="h", url="u", additions=300, deletions=150, changed_files=9)
    )
    plain = card_pull(PullFacts(state="open", head="h", url="u"))
    assert sized is not None
    assert plain is not None
    assert (sized["additions"], sized["deletions"], sized["changed_files"]) == (300, 150, 9)
    assert "additions" not in plain
