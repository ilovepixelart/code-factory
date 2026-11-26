"""The board's columns: which cards sit where, in what order, and what the filters offer."""

from datetime import UTC, datetime
from typing import Any

from code_factory.board.rules.order import rank_key

COLUMNS = ("spec", "build", "review", "merged")
FILTER_GROUPS = ("type", "priority", "label", "assignee", "repository")


def group_columns(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """The cards of each column in order: ranked first, rank 0 last, then by id.

    A released or archived card is off the board.
    """
    columns: dict[str, list[dict[str, Any]]] = {name: [] for name in COLUMNS}
    for card in cards:
        if not card["archived"] and card["stage"] in columns:
            columns[card["stage"]].append(card)
    for column in columns.values():
        column.sort(key=lambda card: rank_key(card["rank"], card["id"]))
    return columns


def options(cards: list[dict[str, Any]]) -> dict[str, list[str]]:
    """The values each filter group offers: sorted, unique, none empty."""
    found: dict[str, set[str]] = {group: set() for group in FILTER_GROUPS}
    for card in cards:
        for group in FILTER_GROUPS:
            value = card["labels"] if group == "label" else [card[group]]
            found[group].update(text for text in value if text)
    return {group: sorted(values) for group, values in found.items()}


def _limits(limits: dict[str, Any]) -> dict[str, int]:
    return {
        name: value
        for name in COLUMNS
        if isinstance(value := limits.get(name), int) and not isinstance(value, bool) and value > 0
    }


def board_answer(
    cards: list[dict[str, Any]],
    limits: dict[str, Any],
    problems: list[dict[str, str]],
    now: datetime,
) -> dict[str, Any]:
    """The board: today, the columns, what could not be read, totals, limits and filter options."""
    columns = group_columns(cards)
    return {
        "today": now.astimezone(UTC).date().isoformat(),
        "columns": columns,
        "problems": problems,
        "totals": {name: len(column) for name, column in columns.items()},
        "limits": _limits(limits),
        "options": options([card for column in columns.values() for card in column]),
    }
