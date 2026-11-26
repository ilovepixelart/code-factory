"""Every card of the board goldens, read back into the facts it was made of, is rebuilt equal.

The facts are the card's own fields set into the model the card rule reads (a field the rule
derives, such as the checklist counts, is not set), so the rule must regenerate each derived value
and the key order, and must keep every optional key absent unless its fact is set.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from board_values import ticket
from code_factory.board.models import CardFacts, Placement, PullFacts, RunCard, RunCost, TicketRuns
from code_factory.board.rules.card import build_card
from code_factory.board.rules.fields import ticket_fields

FORMATS = Path(__file__).parents[1] / "golden/formats"
PAGES = json.loads((FORMATS / "api/tickets.golden.json").read_text())
PAGE_NOW = datetime(2026, 9, 21, 10, tzinfo=UTC)
BOARDS = {
    name: json.loads((FORMATS / name).read_text())
    for name in ("api/board.golden.json", "metrics/board.golden.json")
}
CASES = [
    pytest.param(name, card, id=f"{name.split('/')[0]}-{card['id']}")
    for name, board in BOARDS.items()
    for column in board["columns"].values()
    for card in column
]
QUEUE_KEYS = ("queue", "overlap", "holder")
PULL_KEYS = tuple(PullFacts.model_fields)


def _pull(card: dict[str, Any]) -> PullFacts | None:
    shown = card["pull"]
    return (
        None if shown is None else PullFacts(**{k: v for k, v in shown.items() if k in PULL_KEYS})
    )


def _runs(card: dict[str, Any]) -> TicketRuns:
    return TicketRuns(
        runs=[RunCard(**run) for run in card["runs"]],
        spent=None if isinstance(card["spent"], int) else card["spent"],
        spent_estimated=card.get("spent_estimated", False),
        cost=RunCost(),
        halted=card["halted"],
        limited_until=card["limited_until"],
    )


def facts_of(card: dict[str, Any]) -> CardFacts:
    """The facts the card was made of, taken from its fields."""
    return CardFacts(
        ticket=ticket(
            card["id"],
            repository=card["repository"],
            title=card["title"],
            type=card["type"],
            description=card["description"],
            labels=card["labels"],
            priority=card["priority"],
            assignee=card["assignee"],
            due=card["due"],
            blocked=card["blocked"],
            rank=card["rank"],
            branch=card["branch"],
            archived=card["archived"],
            parent=card["parent"],
        ),
        placement=Placement(
            stage=card["stage"],
            evidence_stage=card["evidence_stage"],
            declared=card["declared"],
            hold=card["hold"],
        ),
        stage_since=card["stage_since"],
        repository_path=card["repository_path"],
        open_questions=card["open_questions"],
        open_blockers=card["links"]["open_blockers"],
        children=card["links"]["children"],
        children_done=card["links"]["children_done"],
        pull=_pull(card),
        check=card["check"],
        runs=_runs(card),
        repository_budget=card["budget"],
        sessions=card["sessions"],
        subagents=card["subagents"],
        delivery_event=card.get("delivery_event"),
        checks_configured=card.get("checks_configured", False),
        queue={k: card[k] for k in QUEUE_KEYS if k in card},
    )


@pytest.mark.parametrize(("name", "card"), CASES)
def test_the_card_rebuilt_from_its_facts_equals_the_golden_card(
    name: str, card: dict[str, Any]
) -> None:
    # The goldens were cut at 10:00 UTC of their `today`; days in a column depend on the hour.
    today = datetime.fromisoformat(BOARDS[name]["today"]).replace(hour=10, tzinfo=UTC)
    rebuilt = build_card(facts_of(card), today)
    assert json.dumps(rebuilt) == json.dumps(card)


def test_the_goldens_hold_every_card_the_plan_names() -> None:
    assert len(CASES) == 44


def _split(text: str) -> list[str]:
    return [word for word in text.split(", ") if word]


def _entered(stage_since: str) -> datetime:
    return datetime.fromisoformat(stage_since) if stage_since else PAGE_NOW


@pytest.mark.parametrize("case", PAGES, ids=lambda case: case["id"])
def test_the_card_of_each_golden_page_is_rebuilt_equal(case: dict[str, Any]) -> None:
    card = case["view"]["card"]
    assert json.dumps(build_card(facts_of(card), PAGE_NOW)) == json.dumps(card)


@pytest.mark.parametrize("case", PAGES, ids=lambda case: case["id"])
def test_the_fields_of_each_golden_page_are_rebuilt_equal(case: dict[str, Any]) -> None:
    fields = case["view"]["ticket"]
    made = ticket(
        fields["id"],
        **{k: fields[k] for k in ("title", "type", "branch", "e2e", "tests", "description")},
        **{k: fields[k] for k in ("priority", "assignee", "due", "blocked", "archived", "rank")},
        **{k: fields[k] for k in ("parent", "budget", "parallel", "source", "steps", "pages")},
        labels=_split(fields["labels"]),
        blocked_by=_split(fields["blocked_by"]),
        caused_by=_split(fields["caused_by"]),
    )
    shown = ticket_fields(made, _entered(fields["stage_since"]), fields["stage"])
    shown["stage_since"] = shown["stage_since"] if fields["stage_since"] else ""
    assert json.dumps(shown) == json.dumps(fields)
