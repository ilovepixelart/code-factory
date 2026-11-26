"""What an entry cites and whether it still exists."""

from collections.abc import Callable
from collections.abc import Set as AbstractSet
from pathlib import PurePosixPath

from code_factory.memory.models import MemoryEntry


def plain_cite(cite: str) -> bool:
    """Whether the cite is a relative path that stays below its root, or a test name."""
    path = PurePosixPath(cite)
    return bool(cite) and not path.is_absolute() and ".." not in path.parts


def gone_cites(
    entry: MemoryEntry, defined: AbstractSet[str], exists: Callable[[str], bool]
) -> list[str]:
    """The cites that no longer exist: neither a path `exists` finds nor a defined test name.

    An absolute or `..` cite counts as gone without asking `exists`.
    """
    cites = [cite.strip() for cite in entry.cites if cite.strip()]
    return [
        cite for cite in cites if cite not in defined and not (plain_cite(cite) and exists(cite))
    ]


def stale_mark(gone: list[str]) -> str:
    """What follows a stale entry's recall line; empty when no cite is gone."""
    return f" [stale: cites {', '.join(gone)} no longer exist]" if gone else ""
