"""What shrinks the active entries: lessons their test now enforces, and entries alike."""

from collections.abc import Sequence
from collections.abc import Set as AbstractSet

from code_factory.memory.models import MemoryEntry
from code_factory.memory_extras.models import Merge, Retire
from code_factory.memory_extras.rules.review import guard_state, stale
from code_factory.memory_extras.rules.similar import alike


def retire_reason(guard: str) -> str:
    """Why a lesson a consolidation retires goes."""
    return f"its guard {guard} is a test now"


def _mergeable(one: MemoryEntry, other: MemoryEntry, defined: AbstractSet[str]) -> bool:
    missing = "missing" in (guard_state(one, defined), guard_state(other, defined))
    first, second = one.guard.strip(), other.guard.strip()
    differ = one.kind == "lesson" and bool(first) and bool(second) and first != second
    return not missing and not differ


def _merges(
    active: Sequence[MemoryEntry], defined: AbstractSet[str], gone: set[str]
) -> list[Merge]:
    by_date = sorted(active, key=lambda e: (e.date, e.id))
    merges = []
    for at, into in enumerate(by_date):
        for source in by_date[at + 1 :]:
            if (
                into.id in gone
                or source.id in gone
                or into.kind != source.kind
                or not alike(into.statement, source.statement)
                or not _mergeable(into, source, defined)
            ):
                continue
            gone.add(source.id)
            merges.append(Merge(from_id=source.id, into=into.id))
    return sorted(merges, key=lambda m: (m.from_id, m.into))


def proposals(
    entries: Sequence[MemoryEntry], defined: AbstractSet[str], now: int
) -> list[Merge | Retire]:
    """The retirements, then the merges, that shrink the active entries, each group in id order.

    A lesson its guard enforces and nobody reviewed for 30 days retires. Of two alike entries of
    one kind the later merges into the earlier. No proposal names an entry an earlier one removed.
    """
    active = sorted((e for e in entries if not e.retired), key=lambda e: e.id)
    retire = [
        Retire(id=e.id, guard=e.guard.strip())
        for e in active
        if guard_state(e, defined) == "enforced" and stale(e, now) and e.kind == "lesson"
    ]
    gone = {r.id for r in retire}
    return [*retire, *_merges(active, defined, gone)]
