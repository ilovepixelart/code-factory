"""The timeline's keyset cursor, worked on entries by hand (no database)."""

from datetime import UTC, datetime, timedelta

from code_factory.tickets.models import ActivityEntry
from code_factory.timeline.rules import page_of, parse_cursor

T1 = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
T2 = T1 + timedelta(minutes=1)
T3 = T1 + timedelta(minutes=2)


def entry(
    at: datetime, entry_id: int, *, source: str = "tickets", kind: str = "note"
) -> ActivityEntry:
    return ActivityEntry(
        at=at, kind=kind, by="", sentence=f"{source}{entry_id}", id=entry_id, source=source
    )


def sentences(entries: list[ActivityEntry]) -> list[str]:
    return [e.sentence for e in entries]


def test_a_cursor_at_a_moment_no_entry_has_starts_at_the_next_later_moment() -> None:
    feed = [entry(T1, 1), entry(T3, 2)]
    first, token = page_of(feed, 1, None, newest_first=False)
    assert sentences(first) == ["tickets1"]
    assert token is not None
    foreign = token.replace(T1.isoformat(), T2.isoformat())
    rest, _ = page_of(feed, 5, parse_cursor(foreign), newest_first=False)
    assert sentences(rest) == ["tickets2"]


def test_a_newest_first_cursor_at_a_moment_no_entry_has_starts_at_the_next_earlier_moment() -> None:
    feed = [entry(T3, 2), entry(T1, 1)]
    first, token = page_of(feed, 1, None, newest_first=True)
    assert sentences(first) == ["tickets2"]
    assert token is not None
    foreign = token.replace(T3.isoformat(), T2.isoformat())
    rest, _ = page_of(feed, 5, parse_cursor(foreign), newest_first=True)
    assert sentences(rest) == ["tickets1"]


def test_a_cursor_past_the_last_entry_gives_an_empty_page() -> None:
    feed = [entry(T1, 1)]
    _, token = page_of([entry(T1, 1), entry(T3, 2)], 2, None, newest_first=False)
    assert token is None
    late = f"{T3.isoformat()}|1|0|9"
    rest, onward = page_of(feed, 5, parse_cursor(late), newest_first=False)
    assert rest == []
    assert onward is None
