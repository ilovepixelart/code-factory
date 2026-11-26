"""One feed of a ticket from the tickets and the talk, paged by a keyset cursor."""

from typing import get_args

from code_factory.talk.models import EntryKind, TalkEntry
from code_factory.talk.service import TalkService
from code_factory.tickets.service import ActivityService, merge_entries
from code_factory.timeline.models import TimelinePage
from code_factory.timeline.rules import page_of, page_size, parse_cursor, talk_entry

TALK_PAGE = 100


class TimelineService:
    """A ticket's history and talk read as one timeline."""

    def __init__(
        self, activity: ActivityService, talk: TalkService, *, talk_page: int = TALK_PAGE
    ) -> None:
        self._activity = activity
        self._talk = talk
        self._talk_page = talk_page

    async def list_activity(  # the feed's one question
        self,
        ticket: str,
        *,
        kinds: list[str] | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        newest_first: bool = False,
    ) -> TimelinePage:
        """The ticket's records and talk as one feed, oldest first unless `newest_first`.

        Entries of one moment keep the order of the sources (history, then talk) and their own
        order within each, in both directions. At most `limit` (25 by default, 100 at most) come
        back; `next_cursor` continues after the last one. The feed is read whole and cut, so a
        page costs the length of the ticket's history.
        """
        size = page_size(limit)
        after = parse_cursor(cursor)
        history = await self._activity.entries(ticket)
        talk = [talk_entry(e) for e in await self._talk_entries(ticket, kinds)]
        merged = merge_entries([history, talk], newest_first=newest_first)
        wanted = [e for e in merged if kinds is None or e.kind in kinds]
        items, next_cursor = page_of(wanted, size, after, newest_first=newest_first)
        return TimelinePage(items=items, next_cursor=next_cursor)

    async def _talk_entries(self, ticket: str, kinds: list[str] | None) -> list[TalkEntry]:
        talk_kinds: list[EntryKind] = [
            k for k in get_args(EntryKind) if kinds is None or k in kinds
        ]
        entries: list[TalkEntry] = []
        cursor: str | None = None
        while talk_kinds:
            page = await self._talk.activity_entries(
                ticket, talk_kinds, limit=self._talk_page, cursor=cursor
            )
            entries += page.items
            cursor = page.next_cursor
            if cursor is None:
                break
        return entries
