"""The Memory page: every tracked repository's lists, queue, pairs and search results."""

import builtins
from dataclasses import dataclass, field
from datetime import datetime

from code_factory.memory_extras.models import (
    Found,
    History,
    LeftOut,
    MemoryPage,
    MergeProposal,
    PairRecord,
    Receipt,
    Record,
    RetireProposal,
    TicketContext,
)
from code_factory.memory_extras.repository import DeliveryRepository
from code_factory.memory_extras.rules import overflow, recall_size, within_budget
from code_factory.memory_extras.rules.constants import BUDGET
from code_factory.memory_extras.service.base import View
from code_factory.memory_extras.service.knowledge import KnowledgeMixin
from code_factory.memory_extras.service.recall import applied
from code_factory.memory_extras.service.records import (
    history,
    pair_records,
    proposal_records,
    queued,
    record_of,
)
from code_factory.platform.text import Paging


@dataclass
class RepositoryRead:
    """One repository's part of the page."""

    records: builtins.list[Record] = field(default_factory=list)
    history: builtins.list[History] = field(default_factory=list)
    left_out: builtins.list[LeftOut] = field(default_factory=list)
    pairs: builtins.list[PairRecord] = field(default_factory=list)
    proposals: builtins.list[MergeProposal | RetireProposal] = field(default_factory=list)
    queue: builtins.list[Record] = field(default_factory=list)
    loaded_chars: int = 0
    rules_over: int = 0


def _by_entry(receipts: builtins.list[Receipt]) -> dict[str, builtins.list[Receipt]]:
    found: dict[str, builtins.list[Receipt]] = {}
    for receipt in receipts:
        found.setdefault(receipt.entry_id, []).append(receipt)
    return found


def read_repository(view: View, receipts: builtins.list[Receipt], now: int) -> RepositoryRead:
    """Everything the page shows of one repository, from what was read of it."""
    every = applied(view, TicketContext())
    marks = {a.entry.id: len(a.mark) for a in every}
    size = lambda entry: marks[entry.id]  # noqa: E731
    entries = [a.entry for a in every]
    _, left = within_budget(entries, size)
    left_ids = frozenset(e.id for e in left)
    received = _by_entry(receipts)
    records = [record_of(e, view, left_ids, received.get(e.id, []), now) for e in view.current]
    queue = [r for r, e in zip(records, view.current, strict=True) if queued(r, e, now)]
    return RepositoryRead(
        records=records,
        history=history(view),
        left_out=[LeftOut(repository=view.repository, id=e.id) for e in left],
        pairs=pair_records(view, now),
        proposals=proposal_records(view, now),
        queue=queue,
        loaded_chars=sum(recall_size(e, size(e)) for e in entries),
        rules_over=overflow(entries, size),
    )


class PageMixin(KnowledgeMixin):
    """The owner's read of memory."""

    async def _read(self, repository: str, now: datetime) -> RepositoryRead:
        view = await self.with_cites(await self._view(repository, now))
        async with self._uow() as session:
            receipts = await DeliveryRepository(session).receipts(repository)
        return read_repository(view, receipts, self._day(now))

    def today(self) -> str:
        """Today as the service's clock reads it, `YYYY-MM-DD`."""
        return self._today()

    async def repositories(self) -> builtins.list[str]:
        """The names of the tracked repositories."""
        return [r.name for r in await self._repositories.list()]

    async def pairs(
        self, repository: str, now: datetime | None = None
    ) -> builtins.list[PairRecord]:
        """The pairs of current entries on one subject."""
        view = await self._view(repository, now)
        return pair_records(view, self._day(now))

    async def proposals(
        self, repository: str, now: datetime | None = None
    ) -> builtins.list[MergeProposal | RetireProposal]:
        """The merges and retirements a consolidation proposes."""
        view = await self._view(repository, now)
        return proposal_records(view, self._day(now))

    async def review_queue(
        self, repository: str, now: datetime | None = None
    ) -> builtins.list[Record]:
        """The entries waiting for review (overdue, citing what is gone, unused), by due day."""
        read = await self._read(repository, now or self._clock())
        return sorted(read.queue, key=lambda r: (r.review_due, r.id))

    async def _results(
        self, repositories: builtins.list[str], query: str, paging: Paging
    ) -> tuple[builtins.list[Found], int]:
        upto = paging.page * paging.size
        results: builtins.list[Found] = []
        matched = 0
        for name in repositories:
            found, count = await self.knowledge(name, query, upto)
            results += found
            matched += count
        return results, matched

    async def page(
        self, query: str, paging: Paging | None = None, now: datetime | None = None
    ) -> MemoryPage:
        """The whole Memory page; `query` searches knowledge and `paging` pages its results."""
        stamp = now or self._clock()
        names = [r.name for r in await self._repositories.list()]
        reads = [await self._read(name, stamp) for name in names]
        records = [r for read in reads for r in read.records]
        reviewed = [r for r in records if r.reviewed]
        results, matched = (
            await self._results(names, query.strip(), paging or Paging.FIRST)
            if query.strip()
            else ([], 0)
        )
        shown = (paging or Paging.FIRST).within(matched)
        start = (shown.page - 1) * shown.size
        queue = [r for read in reads for r in read.queue]
        return MemoryPage(
            repositories=names,
            unreviewed=[r for r in records if not r.reviewed],
            rules=[r for r in reviewed if r.kind == "rule"],
            decisions=[r for r in reviewed if r.kind == "decision"],
            lessons=[r for r in reviewed if r.kind == "lesson"],
            retired=[h for read in reads for h in read.history],
            loaded_chars=sum(read.loaded_chars for read in reads),
            ceiling=BUDGET,
            rules_over=sum(read.rules_over for read in reads),
            left_out=[x for read in reads for x in read.left_out],
            pairs=[p for read in reads for p in read.pairs],
            results=results[start : start + shown.size],
            matched=matched,
            page=shown.page,
            size=shown.size,
            proposals=[p for read in reads for p in read.proposals],
            review_queue=sorted(queue, key=lambda r: (r.review_due, r.id)),
        )
