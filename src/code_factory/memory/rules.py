"""Pure memory rules: entry names, what an entry may hold, review dates, search and recall."""

import re
from datetime import date, timedelta

from code_factory.memory.models import MemoryEntry, MemoryFields, Stage
from code_factory.platform.errors import BadRequestError

_LABEL = "label:"

SLUG_WORDS = 8
_WORD = re.compile(r"[a-z0-9]+")


def slug(words: str) -> str:
    """An entry's name from its first eight words, lower case, joined by hyphens.

    Words are runs of ASCII letters and digits; `record` when there are none.
    """
    found = [match.group() for match in _WORD.finditer(words.lower())][:SLUG_WORDS]
    return "-".join(found) if found else "record"


def entry_name(day: date, statement: str, taken: set[str]) -> str:
    """`<day>-<slug>`, numbered `-2`, `-3` while the name is taken (active or retired)."""
    base = f"{day.isoformat()}-{slug(statement)}"
    name, number = base, 1
    while name in taken:
        number += 1
        name = f"{base}-{number}"
    return name


STAGES = ("spec", "build", "review")
CORE = "core"
ARCHIVE = "archive"
REVIEW_DAYS = 90
STALE_DAYS = 30
BUDGET = 8_000
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def terms(scope: str) -> list[str]:
    """The terms of a scope, separated by commas; none for an empty scope."""
    return [term.strip() for term in scope.split(",") if term.strip()]


def _known_term(term: str) -> bool:
    label = term.removeprefix(_LABEL)
    is_label = term.startswith(_LABEL) and bool(label)
    is_glob = not term.startswith(_LABEL) and any(c in term for c in "/*?[.")
    return term in {CORE, ARCHIVE, *STAGES} or is_label or is_glob


def _is_day(text: str) -> bool:
    if not _DAY.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def check_entry(statement: str, fields: MemoryFields) -> None:
    """`BadRequestError` naming why an entry cannot be written as it is."""
    if not statement.strip():
        raise BadRequestError("an entry needs a statement: say what to do")
    lines = (
        fields.why,
        fields.source,
        fields.guard,
        fields.scope,
        *fields.supersedes,
        *fields.cites,
    )
    if any("\n" in line for line in lines):
        raise BadRequestError("why, source, guard, scope, supersedes and cites are one line each")
    if fields.expires and not _is_day(fields.expires):
        raise BadRequestError("expires is a date, YYYY-MM-DD")
    if any(c.isspace() for c in fields.until):
        raise BadRequestError("until names one ticket id")
    scope = terms(fields.scope)
    if not all(_known_term(term) for term in scope):
        msg = (
            "scope names core, archive, spec, build, review, label:<name> or a path glob, "
            "separated by commas"
        )
        raise BadRequestError(msg)
    if ARCHIVE in scope and len(scope) > 1:
        raise BadRequestError("archive is a scope of its own: it combines with no other term")


def check_new(statement: str, fields: MemoryFields) -> None:
    """`check_entry`, and a new entry names its source (an older one may lack it)."""
    check_entry(statement, fields)
    if not fields.source.strip():
        raise BadRequestError(
            "an entry needs a source: the ticket, run or conversation it came from"
        )


def _last_review(written: date, reviewed: str) -> date:
    return date.fromisoformat(reviewed) if _is_day(reviewed) else written


def review_due(written: date, reviewed: str) -> str:
    """The day an entry falls due for review: 90 days after its last review, or its writing."""
    return (_last_review(written, reviewed) + timedelta(days=REVIEW_DAYS)).isoformat()


def is_stale(written: date, reviewed: str, today: date) -> bool:
    """Whether more than 30 days passed since the entry was last reviewed, or written."""
    return (today - _last_review(written, reviewed)).days > STALE_DAYS


def is_incomplete(statement: str, why: str, source: str) -> bool:
    """Whether the entry lacks its statement, its why or its source."""
    return any(not text.strip() for text in (statement, why, source))


def matches(query: str, *texts: str) -> bool:
    """Whether every word of `query`, ignoring case, is in the texts joined by spaces."""
    haystack = " ".join(texts).lower()
    return all(word in haystack for word in query.lower().split())


def recall_line(entry: MemoryEntry) -> str:
    """The line a session reads for an entry: the statement, then its why."""
    if entry.why:
        return f"- {entry.statement} Why: {entry.why}"
    return f"- {entry.statement}"


def _loads_in(entry: MemoryEntry, stage: Stage, today: date) -> bool:
    scope = terms(entry.scope)
    lapsed = bool(entry.expires) and entry.expires < today.isoformat()
    applies = not scope or CORE in scope or stage in scope
    return entry.status == "active" and not lapsed and applies


def _rank(entry: MemoryEntry) -> int:
    if CORE in terms(entry.scope):
        return 0
    return 2 if entry.kind == "lesson" else 1


def recall(entries: list[MemoryEntry], stage: Stage, today: date) -> str:
    """The text a run of `stage` is given: one line per entry it loads, within the budget.

    It loads active entries whose scope is empty, `core` or names the stage, not past `expires`:
    core entries first, then rules and decisions, then lessons, each group newest first. Lines
    that would pass 8000 characters are left out.
    """
    loaded = sorted(
        (e for e in entries if _loads_in(e, stage, today)),
        key=lambda e: (_rank(e), -e.date.toordinal()),
    )
    lines, size = [], 0
    for entry in loaded:
        line = recall_line(entry)
        if size + len(line) + 1 > BUDGET:
            continue
        lines.append(line)
        size += len(line) + 1
    return "".join(f"{line}\n" for line in lines)
