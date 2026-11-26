"""The order sessions load entries in, and the budget that cuts it."""

from collections.abc import Callable, Sequence

from code_factory.memory.models import MemoryEntry
from code_factory.memory_extras.rules.constants import BUDGET, TITLE_CHARS
from code_factory.memory_extras.rules.scope import is_core

Mark = Callable[[MemoryEntry], int]


def _no_mark(_entry: MemoryEntry) -> int:
    return 0


def recall_line(entry: MemoryEntry) -> str:
    """The line a session reads: the statement, then its why."""
    return f"- {entry.statement} Why: {entry.why}" if entry.why else f"- {entry.statement}"


def recall_size(entry: MemoryEntry, mark: int = 0) -> int:
    """The characters the line takes with its line end and the `mark` characters after it."""
    return len(recall_line(entry)) + 1 + mark


_CORE, _RULE, _LESSON = 0, 1, 2


def _rank(entry: MemoryEntry) -> int:
    if is_core(entry):
        return _CORE
    return _LESSON if entry.kind == "lesson" else _RULE


def _in_load_order(entries: Sequence[MemoryEntry]) -> list[MemoryEntry]:
    """Core first, then rules and decisions, then lessons, each newest first by (date, id)."""
    newest = sorted(entries, key=lambda e: (e.date, e.id), reverse=True)
    return sorted(newest, key=_rank)


def within_budget(
    entries: Sequence[MemoryEntry], mark: Mark = _no_mark
) -> tuple[list[MemoryEntry], list[MemoryEntry]]:
    """The entries in load order, split into kept and left out.

    Core entries, rules and decisions are always kept. Lessons are kept while the running total
    stays within 8000 characters; the first that does not fit and every lesson after it are left
    out.
    """
    ordered = _in_load_order(entries)
    used, kept = 0, 0
    for entry in ordered:
        used += recall_size(entry, mark(entry))
        if _rank(entry) == _LESSON and used > BUDGET:
            break
        kept += 1
    return ordered[:kept], ordered[kept:]


def overflow(entries: Sequence[MemoryEntry], mark: Mark = _no_mark) -> int:
    """The characters the always-kept entries take past the budget."""
    always = sum(recall_size(e, mark(e)) for e in entries if _rank(e) < _LESSON)
    return max(always - BUDGET, 0)


def title(line: str) -> str:
    """The statement of a recall line, cut to 60 characters."""
    statement = line.removeprefix("- ")
    return statement.split(" Why: ", maxsplit=1)[0][:TITLE_CHARS]
