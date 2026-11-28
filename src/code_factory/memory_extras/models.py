"""What the memory-extras rules and service take and answer.

The page models declare their fields in the order the Memory page's answer lists them.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from code_factory.memory.models import EntryImage, MemoryEntry

UNDO_KIND = "memory.restore"


class Frozen(BaseModel):
    """Values are compared and shared, never edited."""

    model_config = ConfigDict(frozen=True)


class TicketContext(Frozen):
    """What decides which entries a run is given.

    The run's stage, the paths its branch changes and its ticket's labels.
    """

    stage: str = ""
    paths: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()


class Applied(Frozen):
    """An entry a context loads, with the mark its recall line carries (a stale mark or empty)."""

    entry: MemoryEntry
    mark: str = ""


class Recall(Frozen):
    """What a run is given: its lines within the budget, what the budget cut, the archive index.

    `received` are the ids of the entries in `lines` (the lines of `lines` in order);
    `digest` is the first 12 hex characters of the SHA-256 of the lines joined by newlines.
    """

    lines: tuple[str, ...]
    left_out: tuple[str, ...]
    overflow_line: str
    index: tuple[str, ...]
    received: tuple[str, ...]
    digest: str


class Restore(Frozen):
    """The row images that put a change back."""

    images: tuple[EntryImage, ...]


class MemoryChanged(Frozen):
    """What a write answers: the notice and how to take it back."""

    notice: str
    restore: Restore


class Pair(Frozen):
    """Two active entries on one subject, for the owner to read together."""

    one: str
    other: str
    terms: tuple[str, ...]
    contradicts: bool


class Merge(Frozen):
    """Fold the entry `from_id` into `into`."""

    from_id: str
    into: str


class Retire(Frozen):
    """Retire the lesson `id`, whose `guard` is a test now."""

    id: str
    guard: str


class Choice(Frozen):
    """One answer to a question."""

    text: str
    recommended: bool
    reason: str


class DuplicateQuestion(Frozen):
    """A question asking whether a new ticket is the same change as an open one."""

    ticket_id: str
    text: str
    choices: tuple[Choice, ...]


class Delivery(Frozen):
    """An entry a run was given."""

    entry_id: str
    left_out: bool = False


class ReceivedBy(BaseModel):
    """A run that received an entry."""

    run: str
    ticket_id: str


class Record(BaseModel):
    """An active entry as the Memory page lists it."""

    id: str
    kind: str
    date: str
    source: str
    statement: str
    why: str
    guard: str
    repository: str
    reviewed: str
    guard_state: str
    loaded: bool
    left_out: bool
    superseded_by: str
    scope: str
    supersedes: str
    loads: str
    chars: int
    proposed: bool
    stale: bool
    incomplete: bool
    review_due: str
    filing: str = "committed"
    cites: str
    stale_cites: list[str]
    received_by: list[ReceivedBy]
    received_count: int
    last_received: str
    unused: bool


class History(BaseModel):
    """A retired or ended entry as the Memory page lists it under History."""

    id: str
    kind: str
    date: str
    source: str
    statement: str
    why: str
    guard: str
    repository: str
    retired: str
    merged_into: str


class LeftOut(BaseModel):
    """An entry the budget left out of recall."""

    repository: str
    id: str


class PairRecord(BaseModel):
    """A pair with both statements."""

    repository: str
    one: str
    other: str
    one_statement: str
    other_statement: str
    terms: list[str]
    contradicts: bool


class MergeProposal(BaseModel):
    """A consolidation that merges an entry into another."""

    repository: str
    action: Literal["merge"] = "merge"
    statement: str
    into_statement: str
    id: str
    into: str


class RetireProposal(BaseModel):
    """A consolidation that retires a lesson its guard now enforces."""

    repository: str
    action: Literal["retire"] = "retire"
    statement: str
    reason: str
    id: str
    guard: str


class Found(BaseModel):
    """A knowledge search result: where it is, a snippet and the address that opens it."""

    repository: str
    path: str
    snippet: str
    open: str


class MemoryPage(BaseModel):
    """The Memory page's whole answer."""

    repositories: list[str]
    unreviewed: list[Record]
    rules: list[Record]
    decisions: list[Record]
    lessons: list[Record]
    retired: list[History]
    loaded_chars: int
    ceiling: int
    rules_over: int
    left_out: list[LeftOut]
    pairs: list[PairRecord]
    unreadable: list[str] = Field(default_factory=list)
    results: list[Found]
    matched: int
    page: int
    size: int
    proposals: list[MergeProposal | RetireProposal]
    review_queue: list[Record]
    filing: None = None


class Doc(Frozen):
    """A document the knowledge search reads: where it is and what it says."""

    path: str
    text: str


class Receipt(Frozen):
    """A run that was given an entry, and when."""

    entry_id: str
    run_id: str
    ticket_id: str
    at: datetime
