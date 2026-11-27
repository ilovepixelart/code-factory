"""Tickets the board files by itself: recurring entries."""

from collections.abc import Iterable, Mapping
from datetime import datetime

from code_factory.follower.rules.periods import period

TYPES = {"feature", "bug", "refactor", "upgrade", "hotfix", "docs"}


def recurring_source(title: str, when: str) -> str:
    """The source that makes a recurring ticket once per period."""
    return f"recurring:{title}@{when}"


def recurring_due(
    entries: Iterable[Mapping[str, object]], known: set[str], now: datetime
) -> list[dict[str, object]]:
    """The recurring tickets to file now: fields of each, its source not yet filed."""
    due: list[dict[str, object]] = []
    for entry in entries:
        title = str(entry.get("title") or "").strip()
        when = period(str(entry.get("every") or ""), now)
        kind = str(entry.get("type") or "")
        if not title or not when or (kind and kind not in TYPES):
            continue
        source = recurring_source(title, when)
        if source in known:
            continue
        due.append({"title": title, "source": source, **_optional_fields(entry, kind)})
    return due


def _optional_fields(entry: Mapping[str, object], kind: str) -> dict[str, object]:
    fields: dict[str, object] = {}
    if kind:
        fields["type"] = kind
    if entry.get("description"):
        fields["description"] = str(entry["description"])
    if entry.get("labels"):
        fields["labels"] = [s.strip() for s in str(entry["labels"]).split(",") if s.strip()]
    return fields


def _caused_by(ticket: str | None) -> dict[str, object]:
    return {} if ticket is None or not ticket else {"caused_by": [ticket]}


def main_failure_fields(  # noqa: PLR0913  # the failing run's facts, all named
    *, repository: str, commit: str, step: str, broken_by: str, passed: str, ticket: str
) -> dict[str, object]:
    """The bug ticket a failing default branch files: one per breakage, not one per commit.

    A breakage is named by the commit that broke it, else by the last commit that passed, so the
    commits that land while it stays broken file nothing more.
    """
    since = broken_by or (f"after {passed}" if passed else commit)
    where = f" {step}" if step else ""
    blame = f" Broken by {broken_by[:7]}." if broken_by else ""
    return {
        "title": f"{repository}: main fails{where} at {commit[:7]}",
        "type": "bug",
        "description": (
            f"The default branch's own checks fail{where} at {commit}.{blame} "
            "Fix it before more work merges on top."
        ),
        "source": f"main:{since}",
        **_caused_by(ticket),
    }


def revert_fields(title: str, branch: str, ticket: str | None) -> dict[str, object]:
    """The bug ticket a reverted merge files: the work came back out and is owed again."""
    named = ticket or branch
    return {
        "title": f"Reverted: {title}",
        "type": "bug",
        "description": (
            f"The merge of {named} was reverted on the default branch. Find why it did not "
            "hold, and land it again with a test that would have caught it."
        ),
        "source": f"revert:{branch}",
        **_caused_by(ticket),
    }
