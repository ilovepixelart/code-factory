"""Where an entry loads: the terms of its `scope`."""

from collections.abc import Sequence

from code_factory.memory.models import MemoryFields
from code_factory.memory_extras.rules.constants import ARCHIVE, CORE, LABEL, ROLES
from code_factory.platform.text import name_matches

_GLOB_MARKS = "/*?[."
SCOPE_SENTENCE = (
    "scope names core, archive, spec, build, review, label:<name> or a path glob, "
    "separated by commas"
)
ARCHIVE_SENTENCE = "archive is a scope of its own: it combines with no other term"


def terms(scope: str) -> list[str]:
    """The terms of a scope, split on commas and stripped; a blank scope has one empty term."""
    return [term.strip() for term in scope.split(",")]


def label_of(term: str) -> str | None:
    """The label a `label:<name>` term names; None for another term or an empty name."""
    name = term.removeprefix(LABEL)
    return name if term.startswith(LABEL) and name else None


def is_glob(term: str) -> bool:
    """Whether the term reads as a path glob rather than a word."""
    return not term.startswith(LABEL) and any(mark in term for mark in _GLOB_MARKS)


def _known(term: str) -> bool:
    return term in {CORE, ARCHIVE, *ROLES} or label_of(term) is not None or is_glob(term)


def scope_refusal(fields: MemoryFields) -> str | None:
    """The sentence naming why the scope cannot be written, or None."""
    if not fields.scope.strip():
        return None
    scope = terms(fields.scope)
    if not all(_known(term) for term in scope):
        return SCOPE_SENTENCE
    if ARCHIVE in scope and len(scope) > 1:
        return ARCHIVE_SENTENCE
    return None


def is_archived(fields: MemoryFields) -> bool:
    """Whether the entry is searched on demand and listed in the index, never preloaded."""
    return ARCHIVE in terms(fields.scope)


def is_core(fields: MemoryFields) -> bool:
    """Whether every session loads the entry first."""
    return CORE in terms(fields.scope)


def everywhere(fields: MemoryFields) -> bool:
    """Whether every session loads the entry: no scope, or `core`."""
    return not fields.scope.strip() or is_core(fields)


def for_role(fields: MemoryFields, stage: str) -> bool:
    """Whether the runs of `stage` read the entry; a stage outside the roles reads none."""
    return stage in ROLES and stage in terms(fields.scope)


def for_labels(fields: MemoryFields, labels: Sequence[str]) -> bool:
    """Whether a `label:` term names one of the ticket's labels."""
    named = {name for term in terms(fields.scope) if (name := label_of(term)) is not None}
    return not named.isdisjoint(labels)


def touches(fields: MemoryFields, paths: Sequence[str]) -> bool:
    """Whether a glob of the scope matches one of the paths; `*` crosses folders."""
    globs = [term for term in terms(fields.scope) if is_glob(term)]
    return any(name_matches(path, glob) for glob in globs for path in paths)


def _words(term: str) -> str:
    if term == ARCHIVE:
        return "searched on demand, listed in the index"
    label = label_of(term)
    if label is not None:
        return f"tickets labelled {label}"
    return f"sessions changing {term}" if is_glob(term) else f"{term} runs"


def loads(fields: MemoryFields) -> str:
    """Where the entry loads, in the page's words."""
    if not fields.scope.strip():
        return "every session"
    if is_core(fields):
        return "every session, first"
    return "; ".join(_words(term) for term in terms(fields.scope))
