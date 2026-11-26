"""The Memory page's rows, built from a view and the receipts."""

import builtins
from collections.abc import Sequence

from code_factory.memory.models import MemoryEntry
from code_factory.memory_extras.models import (
    History,
    MergeProposal,
    PairRecord,
    Receipt,
    ReceivedBy,
    Record,
    RetireProposal,
)
from code_factory.memory_extras.models import Merge as MergeStep
from code_factory.memory_extras.rules import (
    guard_state,
    incomplete,
    is_archived,
    loaded,
    loads,
    overdue,
    pairs,
    proposals,
    recall_size,
    retire_reason,
    review_due,
    stale,
    unused,
)
from code_factory.memory_extras.service.base import View
from code_factory.platform.text import day_text, epoch_day


def record_of(
    entry: MemoryEntry,
    view: View,
    left: frozenset[str],
    received: Sequence[Receipt],
    now: int,
) -> Record:
    """An active entry as the page lists it."""
    by = view.replaced.get(entry.id, "")
    is_left = entry.id in left
    is_loaded = loaded(entry, view.defined) and not by and not is_left
    last = day_text(epoch_day(max(r.at for r in received))) if received else ""
    held = entry.proposed or (not is_loaded and not is_left) or is_archived(entry)
    return Record(
        id=entry.id,
        kind=entry.kind,
        date=entry.date.isoformat(),
        source=entry.source,
        statement=entry.statement,
        why=entry.why,
        guard=entry.guard,
        repository=entry.repository,
        reviewed=entry.reviewed,
        guard_state=guard_state(entry, view.defined),
        loaded=is_loaded,
        left_out=is_left,
        superseded_by=by,
        scope=entry.scope,
        supersedes=", ".join(entry.supersedes),
        loads=loads(entry),
        chars=recall_size(entry),
        proposed=entry.proposed,
        stale=stale(entry, now),
        incomplete=incomplete(entry),
        review_due=review_due(entry),
        cites=", ".join(entry.cites),
        stale_cites=view.gone.get(entry.id, []),
        received_by=[ReceivedBy(run=r.run_id, ticket_id=r.ticket_id) for r in received],
        received_count=len(received),
        last_received=last,
        unused=not held and unused(entry, last or None, now),
    )


def queued(record: Record, entry: MemoryEntry, now: int) -> bool:
    """Whether the entry waits in the review queue: overdue, citing what is gone, or unused."""
    return overdue(entry, now) or bool(record.stale_cites) or record.unused


def _lapse_text(entry: MemoryEntry) -> str:
    if entry.until.strip():
        return f"ended when {entry.until.strip()} merged"
    return f"expired {entry.expires.strip()}"


def history_of(entry: MemoryEntry, *, ended: bool) -> History:
    """An entry that ended or was retired, as History lists it."""
    return History(
        id=entry.id,
        kind=entry.kind,
        date=entry.date.isoformat(),
        source=entry.source,
        statement=entry.statement,
        why=entry.why,
        guard=entry.guard,
        repository=entry.repository,
        retired=_lapse_text(entry) if ended else entry.retired,
        merged_into="" if ended else entry.merged_into,
    )


def history(view: View) -> builtins.list[History]:
    """The entries that ended, then the retired ones, oldest first."""
    ended = [history_of(e, ended=True) for e in view.entries if e.id in view.ended]
    gone = [history_of(e, ended=False) for e in view.retired]
    return [*ended, *gone]


def pair_records(view: View, now: int) -> builtins.list[PairRecord]:
    """The pairs of current entries on one subject, each with both statements."""
    said = {e.id: e.statement for e in view.current}
    return [
        PairRecord(
            repository=view.repository,
            one=p.one,
            other=p.other,
            one_statement=said[p.one],
            other_statement=said[p.other],
            terms=list(p.terms),
            contradicts=p.contradicts,
        )
        for p in pairs(view.current, view.defined, now)
    ]


def proposal_records(view: View, now: int) -> builtins.list[MergeProposal | RetireProposal]:
    """The consolidation proposals over the current entries, with the statements they name."""
    said = {e.id: e.statement for e in view.current}
    found: builtins.list[MergeProposal | RetireProposal] = []
    for step in proposals(view.current, view.defined, now):
        if isinstance(step, MergeStep):
            found.append(
                MergeProposal(
                    repository=view.repository,
                    statement=said[step.from_id],
                    into_statement=said[step.into],
                    id=step.from_id,
                    into=step.into,
                )
            )
        else:
            found.append(
                RetireProposal(
                    repository=view.repository,
                    statement=said[step.id],
                    reason=retire_reason(step.guard),
                    id=step.id,
                    guard=step.guard,
                )
            )
    return found
