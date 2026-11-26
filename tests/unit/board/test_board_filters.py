"""The ticket list's filters: widen inside a group, narrow across, flags on any value."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import pytest

from code_factory.board.rules.columns import group_columns
from code_factory.board.rules.filters import LIST_KEYS, TicketsFilter, ticket_list_card

GOLDEN = json.loads(
    (Path(__file__).parents[2] / "support/golden/formats/api/board.golden.json").read_text()
)
CARDS = [card for column in GOLDEN["columns"].values() for card in column]


def listed(query: str) -> dict[str, list[str]]:
    kept = TicketsFilter.from_pairs(parse_qsl(query, keep_blank_values=True))
    columns = group_columns([c for c in CARDS if kept.matches(c)])
    return {name: [c["id"] for c in cards] for name, cards in columns.items()}


@pytest.mark.parametrize("query", sorted(GOLDEN["views"]))
def test_a_query_selects_the_cards_of_the_golden_view(query: str) -> None:
    assert listed(query) == GOLDEN["views"][query]["columns"]


def test_a_value_widens_inside_its_group_and_groups_narrow_each_other() -> None:
    assert listed("type=bug&type=feature&priority=high")["build"] == ["CF-2"]
    assert listed("type=bug&priority=low") == {"spec": [], "build": [], "review": [], "merged": []}


def test_an_unknown_key_and_an_empty_value_filter_nothing() -> None:
    assert listed("unknown=x&type=") == listed("")


def test_a_flag_is_set_by_any_non_empty_value() -> None:
    assert listed("blocked=yes") == listed("blocked=1")
    assert listed("blocked=") == listed("")


def test_a_label_matches_any_label_of_the_card() -> None:
    card: dict[str, Any] = {"labels": ["a", "b"], "blocked": "", "runs": [], "open_questions": 0}
    assert TicketsFilter.from_pairs([("label", "b")]).matches(card)
    assert not TicketsFilter.from_pairs([("label", "c")]).matches(card)


def test_the_list_card_keeps_twenty_fields_and_cuts_the_runs() -> None:
    card = next(c for c in CARDS if c["runs"])
    shown = ticket_list_card(card)
    assert list(shown) == list(LIST_KEYS)
    assert len(shown) == 20
    assert shown["runs"] == [
        {"id": r["id"], "stage": r["stage"], "iteration": r["iteration"]} for r in card["runs"]
    ]


def test_one_open_question_is_enough_for_the_questions_flag() -> None:
    one = {"open_questions": 1}
    none = {"open_questions": 0}
    asking = TicketsFilter.from_pairs([("questions", "1")])
    assert (asking.matches(one), asking.matches(none)) == (True, False)
