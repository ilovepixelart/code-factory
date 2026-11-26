"""The timeline's pure rules: the sentence of a talk entry and the keyset cursor of a page.

An entry has a place in the merged order: its moment, then its source (tickets, then talk), then
the order within the source (a ticket's records by id, the talk by kind and id). A cursor is
`<moment>|<source>|<kind>|<id>`, the place of the last entry on the page; the next page is the
entries after that place, wherever it falls in the list read now, so a record written meanwhile
moves nothing. Newest first reverses the moments only.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import get_args

from code_factory.platform.errors import BadRequestError
from code_factory.talk.models import EntryKind, TalkEntry
from code_factory.tickets.models import ActivityEntry

PAGE_DEFAULT = 25
PAGE_MAX = 100
_SOURCES = ("tickets", "talk")
_KIND_RANK = {kind: rank for rank, kind in enumerate(get_args(EntryKind))}
Place = tuple[int, int, int]


def page_size(limit: int | None) -> int:
    """`limit` held to 1 to 100; 25 when it is not given."""
    return min(max(PAGE_DEFAULT if limit is None else limit, 1), PAGE_MAX)


def talk_entry(entry: TalkEntry) -> ActivityEntry:
    """A record of the talk as a feed entry of the `talk` source."""
    sentence = f"Answered: {entry.text}" if entry.kind == "answer" else entry.text
    return ActivityEntry(
        at=entry.at,
        kind=entry.kind,
        by=entry.by,
        sentence=sentence,
        data={"id": entry.id, **entry.data},
        source="talk",
        id=entry.id,
    )


def _bad_cursor() -> BadRequestError:
    return BadRequestError("that cursor is not one this list gave; start again without it")


def _place(entry: ActivityEntry) -> Place:
    """The entry's order among those of its moment: source, kind within the source, id."""
    source = _SOURCES.index(entry.source) if entry.source in _SOURCES else len(_SOURCES)
    kind = _KIND_RANK.get(entry.kind, 0) if entry.source == "talk" else 0
    return source, kind, entry.id or 0


def _is_place(place: Place) -> bool:
    """Whether the feed can emit this place: a known source and a kind that source has."""
    source, kind, entry_id = place
    kinds = len(_KIND_RANK) if _SOURCES[source : source + 1] == ("talk",) else 1
    return 0 <= source < len(_SOURCES) and 0 <= kind < kinds and entry_id >= 0


def parse_cursor(text: str | None) -> tuple[datetime, Place] | None:
    """The `(moment, place)` a page continues after, `None` for the first page."""
    if text is None or text == "":
        return None
    try:
        when, source, kind, entry_id = text.split("|")
        at = datetime.fromisoformat(when)
        place = (int(source), int(kind), int(entry_id))
    except ValueError:
        raise _bad_cursor() from None
    if at.tzinfo is None or not _is_place(place):
        raise _bad_cursor()
    return at, place


def _is_after(entry: ActivityEntry, after: tuple[datetime, Place], *, newest_first: bool) -> bool:
    moment, place = after
    if entry.at == moment:
        return _place(entry) > place
    return entry.at < moment if newest_first else entry.at > moment


def page_of(
    entries: Sequence[ActivityEntry],
    size: int,
    cursor: tuple[datetime, Place] | None,
    *,
    newest_first: bool,
) -> tuple[list[ActivityEntry], str | None]:
    """The page of `size` entries of the merged `entries` after `cursor`, and the cursor onward."""
    start = 0
    if cursor is not None:
        start = next(
            (i for i, e in enumerate(entries) if _is_after(e, cursor, newest_first=newest_first)),
            len(entries),
        )
    items = list(entries[start : start + size])
    if not items or start + size >= len(entries):
        return items, None
    last = items[-1]
    source, kind, entry_id = _place(last)
    return items, f"{last.at.isoformat()}|{source}|{kind}|{entry_id}"
