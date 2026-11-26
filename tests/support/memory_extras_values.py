"""Values the memory-extras tests share: entries built from plain fields and the frozen clock."""

from datetime import UTC, date, datetime
from typing import Any

from code_factory.memory.models import MemoryEntry

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
OWNER = "owner"


def entry(
    id_: str = "2026-11-10-scoped",
    statement: str = "Scoped",
    kind: str = "rule",
    **fields: Any,  # noqa: ANN401  # any field of the entry
) -> MemoryEntry:
    """An entry as the base service answers it; `date` defaults to the id's first ten characters."""
    values: dict[str, Any] = {
        "repository": "sample",
        "id": id_,
        "kind": kind,
        "statement": statement,
        "date": date.fromisoformat(id_[:10]),
        "source": "owner",
        "why": "",
        "reviewed": "",
        "proposed": False,
        "verdict": "",
        "retired": "",
        "merged_into": "",
        "status": "active",
        "review_due": "",
        "stale": False,
        "incomplete": False,
    }
    values.update(fields)
    if fields.get("retired"):
        values["status"] = "retired"
    return MemoryEntry(**values)
