"""Active entries on one subject, for the owner to read together."""

import re
from collections import Counter
from collections.abc import Sequence
from collections.abc import Set as AbstractSet

from code_factory.memory.models import MemoryEntry
from code_factory.memory_extras.models import Merge, Pair, Retire
from code_factory.memory_extras.rules.consolidation import proposals

DISTINCTIVE = 4
SHARED_TERMS = 3
COMMON = frozenset(
    [
        "about",
        "after",
        "also",
        "been",
        "before",
        "being",
        "could",
        "does",
        "each",
        "every",
        "from",
        "have",
        "into",
        "just",
        "like",
        "made",
        "make",
        "more",
        "most",
        "must",
        "never",
        "once",
        "only",
        "other",
        "over",
        "same",
        "should",
        "some",
        "such",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "until",
        "were",
        "what",
        "when",
        "which",
        "with",
        "without",
    ]
)
NEGATIONS = frozenset({"never", "not", "no", "don't", "without", "stop"})
_WORDS = re.compile(r"[^\W_]+")
_NEGATION_WORDS = re.compile(r"[^\W_']+")
_CLAUSES = re.compile(r"[.;:!?]")
_MIN_LETTERS = 4


def _subject_words(statement: str) -> set[str]:
    return {
        word.lower()
        for word in _WORDS.findall(statement)
        if len(word) >= _MIN_LETTERS and any(c.isalpha() for c in word)
    } - COMMON


def _negates(clause: str) -> bool:
    words = _NEGATION_WORDS.findall(clause.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'"))
    return any(word.lower() in NEGATIONS for word in words)


def _clauses(statement: str, terms: AbstractSet[str]) -> list[tuple[bool, set[str]]]:
    return [
        (_negates(clause), _subject_words(clause) & terms) for clause in _CLAUSES.split(statement)
    ]


def _contradicts(one: str, other: str, terms: AbstractSet[str]) -> bool:
    theirs = _clauses(other, terms)
    return any(
        negated != other_negated and len(words & other_words) >= SHARED_TERMS
        for negated, words in _clauses(one, terms)
        for other_negated, other_words in theirs
    )


def _going(entries: Sequence[MemoryEntry], defined: AbstractSet[str], now: int) -> set[str]:
    return {
        p.from_id if isinstance(p, Merge) else p.id
        for p in proposals(entries, defined, now)
        if isinstance(p, Merge | Retire)
    }


def pairs(entries: Sequence[MemoryEntry], defined: AbstractSet[str], now: int) -> list[Pair]:
    """The pairs of active entries on one subject, in id order.

    Their statements share at least 3 words each held by at most 4 active entries. An entry a
    consolidation would merge away or retire is in none.
    """
    going = _going(entries, defined, now)
    active = sorted((e for e in entries if not e.retired and e.id not in going), key=lambda e: e.id)
    words = [_subject_words(e.statement) for e in active]
    held = Counter(word for found in words for word in found)
    found: list[Pair] = []
    for at, one in enumerate(active):
        for later in range(at + 1, len(active)):
            other = active[later]
            terms = sorted(w for w in words[at] & words[later] if held[w] <= DISTINCTIVE)
            if len(terms) >= SHARED_TERMS:
                shared = set(terms)
                contradicts = _contradicts(one.statement, other.statement, shared)
                found.append(
                    Pair(one=one.id, other=other.id, terms=tuple(terms), contradicts=contradicts)
                )
    return found


def paired_with(
    draft: MemoryEntry, entries: Sequence[MemoryEntry], defined: AbstractSet[str], now: int
) -> str | None:
    """The id of the active entry on the draft's subject, when the draft supersedes nothing."""
    if draft.supersedes:
        return None
    for pair in pairs([*entries, draft], defined, now):
        if draft.id in (pair.one, pair.other):
            return pair.other if pair.one == draft.id else pair.one
    return None
