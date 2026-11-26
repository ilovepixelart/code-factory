"""Whether a new ticket's title looks like an open ticket's, and the question that asks."""

import re

from code_factory.memory_extras.models import Choice, DuplicateQuestion

LETTERS = 4
SHARED = 3
SHARE = 0.6
_WORDS = re.compile(r"[^\W_]+")


def _words(title: str) -> set[str]:
    return {word.lower() for word in _WORDS.findall(title) if len(word) >= LETTERS}


def alike(one: str, other: str) -> bool:
    """Whether two titles share at least 3 words of 4 or more letters and 60% of their words."""
    first, second = _words(one), _words(other)
    shared = len(first & second)
    return shared >= SHARED and shared / max(len(first | second), 1) >= SHARE


def duplicate_questions(title: str, open_tickets: list[tuple[str, str]]) -> list[DuplicateQuestion]:
    """A question for each open ticket (`id`, `title`) the new title is alike."""
    return [
        DuplicateQuestion(
            ticket_id=ticket_id,
            text=f"Is this the same change as {ticket_id} ({other})?",
            choices=(
                Choice(
                    text=f"Merge into {ticket_id}",
                    recommended=True,
                    reason="the titles share most of their words",
                ),
                Choice(text="Keep both", recommended=False, reason="they are different changes"),
            ),
        )
        for ticket_id, other in open_tickets
        if alike(title, other)
    ]
