"""What a run is given: the entries a context loads, within the budget."""

import builtins
import hashlib
from datetime import datetime

from code_factory.memory.models import MemoryEntry
from code_factory.memory_extras.models import Applied, Delivery, Recall, TicketContext
from code_factory.memory_extras.repository import DeliveryRepository
from code_factory.memory_extras.rules import (
    everywhere,
    for_labels,
    for_role,
    is_archived,
    loaded,
    overflow,
    recall_line,
    stale_mark,
    title,
    touches,
    within_budget,
)
from code_factory.memory_extras.rules.constants import BUDGET
from code_factory.memory_extras.service.base import Collaborators, View

DIGEST_CHARS = 12


def loads_now(view: View) -> builtins.list[MemoryEntry]:
    """The current entries sessions load: not proposed, not enforced by a test, not superseded."""
    return [e for e in view.current if loaded(e, view.defined) and e.id not in view.replaced]


def _applies(entry: MemoryEntry, ctx: TicketContext) -> bool:
    return (
        everywhere(entry)
        or touches(entry, ctx.paths)
        or for_labels(entry, ctx.labels)
        or for_role(entry, ctx.stage)
    )


def applied(view: View, ctx: TicketContext) -> builtins.list[Applied]:
    """The entries the context loads.

    An archived entry names no scope a context has: it is the index, never loaded.
    """
    return [
        Applied(entry=e, mark=stale_mark(view.gone.get(e.id, [])))
        for e in loads_now(view)
        if _applies(e, ctx)
    ]


def _overflow_line(over: int) -> str:
    if over == 0:
        return ""
    return (
        f"The rules and decisions above take {over:,} characters over the memory budget of "
        f"{BUDGET:,}: ask the owner to merge, scope or retire one."
    )


def build_recall(view: View, ctx: TicketContext) -> Recall:
    """The lines within the budget, what it cut, the overflow and the archive index."""
    chosen = applied(view, ctx)
    marks = {a.entry.id: a.mark for a in chosen}
    size = lambda entry: len(marks[entry.id])  # noqa: E731
    entries = [a.entry for a in chosen]
    kept, left = within_budget(entries, size)
    lines = tuple(recall_line(e) + marks[e.id] for e in kept)
    index = tuple(
        f"- {e.id}: {title(recall_line(e))}{stale_mark(view.gone.get(e.id, []))}"
        for e in loads_now(view)
        if is_archived(e)
    )
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:DIGEST_CHARS]
    return Recall(
        lines=lines,
        left_out=tuple(e.id for e in left),
        overflow_line=_overflow_line(overflow(entries, size)),
        index=index,
        received=tuple(e.id for e in kept),
        digest=digest,
    )


class RecallMixin(Collaborators):
    """The rules a run is given, and the record of which it received."""

    async def lapsed(self, repository: str, entries: builtins.list[MemoryEntry]) -> frozenset[str]:
        """The ids among the active `entries` that ended: past `expires`, or `until` merged."""
        active = [e for e in entries if not e.retired]
        return await self._ended(repository, active, self._today())

    async def applicable(self, repository: str, ctx: TicketContext) -> builtins.list[Applied]:
        """The entries the context loads, each with the mark its line carries.

        Active, not proposed, not ended, not superseded, not enforced by a test, and loading
        everywhere, or on a changed path, or for a label, or for the context's stage. Archived
        entries are excluded: they are the index.
        """
        return applied(await self.with_cites(await self._view(repository)), ctx)

    async def rules_for(self, repository: str, ctx: TicketContext) -> Recall:
        """What a run of the context is given. Raises `NotFoundError` for an unknown repository."""
        await self._root(repository)
        return build_recall(await self.with_cites(await self._view(repository)), ctx)

    async def deliver(
        self,
        run_id: str,
        ticket_id: str,
        repository: str,
        ctx: TicketContext,
        now: datetime | None = None,
    ) -> Recall:
        """`rules_for`, and the record that the run received (or was cut from) each entry.

        A repeated call for the same run replaces nothing it already holds.
        """
        recall = await self.rules_for(repository, ctx)
        given = [Delivery(entry_id=i) for i in recall.received]
        cut = [Delivery(entry_id=i, left_out=True) for i in recall.left_out]
        async with self._uow() as session:
            await DeliveryRepository(session).record(
                run_id, ticket_id, repository, [*given, *cut], now or self._clock()
            )
        return recall
