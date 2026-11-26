"""The merged activity feed: a sentence for each record this module writes, and the merge."""

from collections.abc import Callable, Sequence
from typing import Any

from code_factory.tickets.models import ActivityEntry


def _text(data: dict[str, Any], key: str) -> str:
    return str(data.get(key, ""))


def _column(data: dict[str, Any], key: str) -> str:
    return _text(data, key).capitalize()


def _stage(data: dict[str, Any]) -> str:
    if "from" in data and "to" in data:
        return f"Moved from {_column(data, 'from')} to {_column(data, 'to')}"
    return "Moved"


def _edited(data: dict[str, Any]) -> str:
    fields = data.get("fields")
    names = [str(f) for f in fields] if isinstance(fields, list) else []
    return f"Edited {', '.join(names)}" if names else "Edited"


_DOCUMENTS = {
    "requirements": "the requirements",
    "mock": "the mock",
    "spec": "the spec",
    "uat": "the UAT plan",
    "review": "the review",
    "notes": "the notes",
}


def _document(data: dict[str, Any]) -> str:
    name = _text(data, "name")
    if not name:
        return "Wrote a document"
    title = _DOCUMENTS.get(name, name)
    if data.get("removed"):
        return f"Removed {title}"
    return f"Wrote {title} (version {_text(data, 'version')})"


_VERDICTS = {"pass": "passed", "changes": "asked for changes"}


def _review(data: dict[str, Any]) -> str:
    verdict = _text(data, "verdict")
    return f"Review {_text(data, 'version')} {_VERDICTS.get(verdict, verdict)}"


_FIELDS = {
    "blocked_by": "blocked by",
    "caused_by": "caused by",
    "e2e": "E2E tests",
    "tests": "unit tests",
}


def _field(data: dict[str, Any]) -> str:
    name = _text(data, "name")
    if name == "description":
        return "Edited the description"
    label = _FIELDS.get(name, name)
    value = _text(data, "value")
    return f"Set {label} to {value}" if value else f"Cleared {label}"


# 137 is a killed container, -1 checks that did not start or were stopped: no verdict either way.
_NO_VERDICT = (137, -1)


def _checks(data: dict[str, Any]) -> str:
    scope = _text(data, "scope")
    name = f"{scope.capitalize()} checks" if scope else "Checks"
    code = data.get("exit_code")
    if not isinstance(code, int) or code in _NO_VERDICT or data.get("outcome") == "killed":
        return f"{name} stopped without a verdict"
    if code == 0:
        return f"{name} passed"
    reason = _text(data, "reason")
    return f"{name} failed: {reason}" if reason else f"{name} failed"


def _capture(data: dict[str, Any]) -> str:
    images = data.get("images")
    count = len(images) if isinstance(images, list) else 0
    return f"Captured {count} screen{'' if count == 1 else 's'}"


def _mock(data: dict[str, Any]) -> str:
    verb = "Removed the" if data.get("removed") else "Kept the"
    return f"{verb} mock image {_text(data, 'name')}"


_SENTENCES: dict[str, Callable[[dict[str, Any]], str]] = {
    "created": lambda d: f"Created as a {_text(d, 'type')}",
    "edited": _edited,
    "stage": _stage,
    "archived": lambda _: "Archived",
    "restored": lambda _: "Put back on the board",
    "document": _document,
    "mock_file": _mock,
    "finding": lambda d: (
        f"Review found {_text(d, 'id')} ({_text(d, 'severity')}): {_text(d, 'text')}"
    ),
    "finding.kept": lambda d: f"Review kept {_text(d, 'id')}",
    "finding.dismissed": lambda d: f"Dismissed {_text(d, 'id')}: {_text(d, 'reason')}",
    "finding.closed": lambda d: (
        f"Closed {_text(d, 'id')} as {_text(d, 'state')}: {_text(d, 'reason')}"
    ),
    "review_submitted": _review,
    "field": _field,
    "checks": _checks,
    "capture": _capture,
    "capture_approved": lambda _: "Approved the screens",
    "capture_changes": lambda d: f"Sent the screens back: {_text(d, 'reason')}",
    "note": lambda d: _text(d, "text"),
    "diagnosis": lambda d: f"Diagnosis: {_text(d, 'text')}",
    "coordinator_edit": lambda d: (
        f"The coordinator set {_text(d, 'name')} from {_text(d, 'from')} to {_text(d, 'to')}"
    ),
}


def describe(kind: str, data: dict[str, Any]) -> str:
    """A record in plain words; a kind this module does not write reads as its own name."""
    sentence = _SENTENCES.get(kind)
    if sentence is not None:
        return sentence(data)
    words = kind.replace("_", " ").replace(".", " ")
    return words[:1].upper() + words[1:]


def merge_entries(
    feeds: Sequence[Sequence[ActivityEntry]], *, newest_first: bool = False
) -> list[ActivityEntry]:
    """The feeds as one, oldest first, or newest first.

    Entries of the same moment keep the order of the feeds and, within a feed, their own.
    """
    entries = (entry for feed in feeds for entry in feed)
    return sorted(entries, key=lambda entry: entry.at, reverse=newest_first)
