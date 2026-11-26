"""The owner's changes to an entry, as the fields each one writes."""

from dataclasses import dataclass
from typing import Any

from code_factory.memory.models import MemoryEdit, MemoryEntry
from code_factory.memory_extras.rules.fields import check_fields
from code_factory.platform.errors import BadRequestError

DISMISSED = "dismissed by the owner"


@dataclass(frozen=True)
class MergePatches:
    """The fields a merge writes: the entry's retirement, and the target's grown source."""

    retired: dict[str, Any]
    target: dict[str, Any] | None


def _clean(value: str | list[str]) -> str | list[str]:
    if isinstance(value, str):
        return value.strip()
    return [part.strip() for part in value if part.strip()]


def edited(entry: MemoryEntry, edit: MemoryEdit, today: str) -> dict[str, Any]:
    """The fields an edit writes: the named ones trimmed, and `reviewed` set to `today`.

    Raises:
        BadRequestError: The entry as edited could not be written.
    """
    changes = {name: _clean(value) for name, value in edit.model_dump(exclude_none=True).items()}
    after = entry.model_copy(update=changes)
    refusal = check_fields(after.kind, after.statement, after, entry.verdict)
    if refusal is not None:
        raise BadRequestError(refusal)
    return {**changes, "reviewed": today}


def _proposal(entry: MemoryEntry) -> None:
    if not entry.proposed:
        raise BadRequestError(f"{entry.id} is not proposed")


def approved(entry: MemoryEntry, today: str) -> dict[str, Any]:
    """The fields that accept a proposal: no longer proposed, reviewed `today`."""
    _proposal(entry)
    return {"proposed": False, "reviewed": today}


def dismissed(entry: MemoryEntry) -> dict[str, Any]:
    """The fields that decline a proposal."""
    _proposal(entry)
    return {"retired": DISMISSED}


def retirement(entry: MemoryEntry, reason: str) -> str:
    """The reason an active entry retires with: one non-empty line.

    Raises:
        BadRequestError: The entry is retired already, or the reason is blank or has two lines.
    """
    if entry.retired:
        raise BadRequestError(f"{entry.id} is retired already")
    said = reason.strip()
    if not said or "\n" in said:
        raise BadRequestError("say in one line why it no longer applies")
    return said


def _sources(source: str) -> list[str]:
    return [part.strip() for part in source.split(";") if part.strip()]


def merge_patches(entry: MemoryEntry, target: MemoryEntry) -> MergePatches:
    """The entry retires naming the target, which gains each source it does not name already."""
    retired = {"retired": f'merged into "{target.statement}"', "merged_into": target.id}
    named = _sources(target.source)
    added = [source for source in _sources(entry.source) if source not in named]
    grown = {"source": "; ".join([*named, *added])} if added else None
    return MergePatches(retired, grown)
