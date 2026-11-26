"""What the memory service takes and answers.

An optional text field is the empty string when unset, as the app reads it.
"""

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryKind = Literal["rule", "decision", "lesson"]
MemoryStatus = Literal["active", "proposed", "retired"]
Stage = Literal["spec", "build", "review"]


class MemoryFields(BaseModel):
    """What an entry says besides its kind and statement."""

    why: str = ""
    source: str = ""
    guard: str = ""
    scope: str = ""
    supersedes: list[str] = Field(default_factory=list)
    expires: str = ""
    until: str = ""
    cites: list[str] = Field(default_factory=list)


class NewMemory(MemoryFields):
    """An entry to record in a repository's memory."""

    repository: str
    kind: MemoryKind
    statement: str


class MemoryEdit(BaseModel):
    """An edit: only the fields given change, and the entry counts as reviewed."""

    kind: MemoryKind | None = None
    statement: str | None = None
    why: str | None = None
    source: str | None = None
    guard: str | None = None
    scope: str | None = None
    supersedes: list[str] | None = None


class MemoryEntry(MemoryFields):
    """An entry as the Memory page shows it; `id` is its name in its repository."""

    repository: str
    id: str
    kind: MemoryKind
    statement: str
    date: date
    reviewed: str
    proposed: bool
    verdict: str
    retired: str
    merged_into: str
    status: MemoryStatus
    review_due: str
    stale: bool
    incomplete: bool


class MemoryFilter(BaseModel):
    """Which entries a list or a search answers."""

    repository: str | None = None
    kinds: list[MemoryKind] | None = None
    status: MemoryStatus = "active"


class Intake(BaseModel):
    """How an entry is being written, as an admission check is told it."""

    by: str
    proposed: bool
    keep_both: bool = False
    check_pairs: bool = False
    now: datetime


# A check another module registers: it raises the platform error that says why a draft may not
# be written. It runs after the base checks and before the insert.
Admission = Callable[[NewMemory, Intake], Awaitable[None]]

# A check split in two: the first part reads files or runs git, so it runs before any transaction
# opens and refuses what it can; it returns the part that runs under the repository's lock.
Preparation = Callable[[NewMemory, Intake], Awaitable[Admission]]


class EntryRecord(MemoryFields):
    """Every stored value of an entry: what a before-image holds and a patch can name.

    `date` is the day it was written. `created_by` and `proposed_by` are the actors that recorded
    and proposed it; `created_at` and `updated_at` are the row's moments.
    """

    model_config = ConfigDict(extra="forbid")

    kind: MemoryKind
    statement: str
    date: date
    reviewed: str = ""
    proposed: bool = False
    verdict: str = ""
    retired: str = ""
    merged_into: str = ""
    created_by: str = ""
    proposed_by: str = ""
    created_at: datetime
    updated_at: datetime


class EntryPatch(BaseModel):
    """Values to write to the entry `id` of `repository`: an update, or an insert when it is new.

    `fields` names `EntryRecord` fields except the row's own moments, which `apply` sets.
    """

    repository: str
    id: str
    fields: dict[str, Any]


class EntryImage(BaseModel):
    """An entry as it was before a patch: `before` is `None` when the patch inserted it.

    `updated_at` is the row's moment right after the patch; `restore` refuses a row that moved on.
    """

    repository: str
    id: str
    before: EntryRecord | None
    updated_at: datetime
