"""Columns, their order, the options the filters offer and the board answer."""

from datetime import UTC, datetime
from typing import Any

from code_factory.board.rules.columns import board_answer, group_columns, options
from code_factory.board.rules.etag import body_of, etag_of

NOW = datetime(2026, 11, 23, 23, 59, 59, tzinfo=UTC)


def card(ticket_id: str, stage: str = "spec", rank: int = 0, **more: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "id": ticket_id,
        "stage": stage,
        "rank": rank,
        "archived": False,
        "type": "feature",
        "priority": "",
        "labels": [],
        "assignee": "",
        "repository": "sample",
    } | more


def ids(cards: list[dict[str, Any]]) -> list[str]:
    return [c["id"] for c in cards]


def test_a_card_sits_in_its_stage_and_the_four_columns_always_exist() -> None:
    columns = group_columns([card("CF-1", "build")])
    assert {name: ids(cards) for name, cards in columns.items()} == {
        "spec": [],
        "build": ["CF-1"],
        "review": [],
        "merged": [],
    }
    assert list(columns) == ["spec", "build", "review", "merged"]


def test_ranked_cards_come_first_and_rank_zero_last() -> None:
    cards = [card("CF-1"), card("CF-10"), card("CF-2", rank=2), card("CF-9", rank=1), card("CF-3")]
    assert ids(group_columns(cards)["spec"]) == ["CF-9", "CF-2", "CF-1", "CF-3", "CF-10"]


def test_released_and_archived_cards_never_appear() -> None:
    cards = [card("CF-1", "released"), card("CF-2", archived=True), card("CF-3")]
    assert ids(group_columns(cards)["spec"]) == ["CF-3"]


def test_two_repositories_merge_in_one_column_order() -> None:
    cards = [card("CF-1", repository="sample"), card("AB-1", repository="second", rank=1)]
    assert ids(group_columns(cards)["spec"]) == ["AB-1", "CF-1"]


def test_options_are_sorted_unique_and_drop_empty_values() -> None:
    cards = [
        card("CF-1", type="feature", priority="low", labels=["ui", "agents"], assignee="alex"),
        card("CF-2", type="bug", priority="", labels=["ui"], assignee="", repository="second"),
        card("CF-3", type="bug", priority="low"),
    ]
    assert options(cards) == {
        "type": ["bug", "feature"],
        "priority": ["low"],
        "label": ["agents", "ui"],
        "assignee": ["alex"],
        "repository": ["sample", "second"],
    }


def test_the_board_answer_has_the_keys_the_app_reads() -> None:
    answer = board_answer([card("CF-1"), card("CF-2", "build")], {"spec": 3}, [], NOW)
    assert list(answer) == ["today", "columns", "problems", "totals", "limits", "options"]
    assert answer["today"] == "2026-11-23"
    assert answer["totals"] == {"spec": 1, "build": 1, "review": 0, "merged": 0}
    assert answer["limits"] == {"spec": 3}
    assert answer["problems"] == []


def test_today_rolls_over_at_utc_midnight() -> None:
    after = datetime(2026, 11, 24, 0, 0, 0, tzinfo=UTC)
    assert board_answer([], {}, [], after)["today"] == "2026-11-24"


def test_an_empty_board_has_four_empty_columns() -> None:
    answer = board_answer([], {}, [], NOW)
    assert answer["columns"] == {"spec": [], "build": [], "review": [], "merged": []}
    assert answer["totals"] == {"spec": 0, "build": 0, "review": 0, "merged": 0}


def test_limits_keep_only_known_columns_with_positive_whole_numbers() -> None:
    limits = {"spec": 2, "build": 0, "review": -1, "merged": "3", "released": 4, "x": 1}
    assert board_answer([], limits, [], NOW)["limits"] == {"spec": 2}


def test_a_boolean_or_a_fraction_is_not_a_limit() -> None:
    assert board_answer([], {"spec": True, "build": 1.5}, [], NOW)["limits"] == {}


def test_the_etag_of_the_empty_text_is_the_first_sixteen_digits_of_its_digest() -> None:
    assert etag_of("") == '"e3b0c44298fc1c14"'


def test_the_etag_of_an_empty_object() -> None:
    assert etag_of("{}") == '"44136fa355b3678a"'


def test_the_body_is_compact_json_that_keeps_unicode() -> None:
    assert body_of({"b": [1, "é"], "a": {}}) == '{"b":[1,"é"],"a":{}}'
    assert body_of({"a": 1}) == '{"a":1}'
