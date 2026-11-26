"""The filters of the ticket list: a query's groups and flags, and the card the list shows."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

LIST_KEYS = (
    "id", "title", "type", "branch", "repository", "stage", "evidence_stage", "description",
    "labels", "priority", "assignee", "due", "blocked", "archived", "rank", "stage_since",
    "checklist", "open_questions", "sessions", "runs",
)  # fmt: skip


GROUPS = ("type", "priority", "label", "assignee", "repository")
FLAGS = ("blocked", "agent", "questions")
_RUN_KEYS = ("id", "stage", "iteration")


@dataclass(frozen=True)
class TicketsFilter:
    """The groups a card must match one value of, and the flags it must satisfy."""

    groups: dict[str, frozenset[str]] = field(default_factory=dict)
    flags: frozenset[str] = frozenset()

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[str, str]]) -> TicketsFilter:
        """The filter a query asks for; an unknown key and an empty value are ignored."""
        groups: dict[str, set[str]] = {}
        flags: set[str] = set()
        for key, value in pairs:
            if not value:
                continue
            if key in GROUPS:
                groups.setdefault(key, set()).add(value)
            elif key in FLAGS:
                flags.add(key)
        return cls({key: frozenset(values) for key, values in groups.items()}, frozenset(flags))

    def matches(self, card: dict[str, Any]) -> bool:
        """Whether the card is in every group asked for and satisfies every flag."""
        return all(
            self._in_group(card, name, wanted) for name, wanted in self.groups.items()
        ) and all(_FLAG_TESTS[flag](card) for flag in self.flags)

    @staticmethod
    def _in_group(card: dict[str, Any], name: str, wanted: frozenset[str]) -> bool:
        have = card["labels"] if name == "label" else [card[name]]
        return any(value in wanted for value in have)


_FLAG_TESTS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "blocked": lambda card: bool(card["blocked"]),
    "agent": lambda card: bool(card["runs"]),
    "questions": lambda card: card["open_questions"] > 0,
}


def ticket_list_card(card: dict[str, Any]) -> dict[str, Any]:
    """The twenty fields the list shows, its runs cut to what names them."""
    shown = {key: card[key] for key in LIST_KEYS}
    shown["runs"] = [{key: run[key] for key in _RUN_KEYS} for run in card["runs"]]
    return shown
