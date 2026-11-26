"""What a board card says holds a ticket, and which open change its text likely overlaps."""

import re
from collections.abc import Collection, Sequence

# The documents a ticket writes at Spec, in order, by the names a card reads.
_DOCUMENT_WORDS = (
    ("requirements", "requirements"),
    ("mock", "mock"),
    ("spec", "spec"),
    ("uat", "UAT"),
)
_WORD = re.compile(r"[\w./-]+")
NEXT = "next, "


def hold_summary(stage: str, detail: str, missing: Collection[str]) -> str:
    """What a card says holds its ticket.

    At Spec with documents missing, their names in the order a ticket writes them, joined in
    words (`requirements, mock, spec and UAT`); otherwise the item's `detail`.
    """
    named = [word for name, word in _DOCUMENT_WORDS if name in missing]
    if stage != "spec" or not named:
        return detail
    if len(named) == 1:
        return named[0]
    return f"{', '.join(named[:-1])} and {named[-1]}"


def named_paths(text: str) -> list[str]:
    """The path-like words of a ticket's text: those holding `/` or `.`, trimmed, sorted, unique."""
    words = (word.strip("./") for word in _WORD.findall(text) if "/" in word or "." in word)
    return sorted({word for word in words if word})


def overlap(named: Sequence[str], open_changes: Sequence[tuple[str, Sequence[str]]]) -> str | None:
    """The first open change with a file a named path equals or is a folder of."""
    for label, files in open_changes:
        for file in files:
            if any(file == path or file.startswith(f"{path}/") for path in named):
                return f"likely overlaps {label} in {file}"
    return None


def queue_note(card_overlap: str, reason: str) -> str:
    """The queue's word for a planned ticket: the cap that holds it, else `next` and its overlap."""
    if not reason and card_overlap:
        return f"{NEXT}{card_overlap}"
    return reason
