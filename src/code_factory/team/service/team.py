"""The team module's public API: claims, status reads and the Team page, over one unit of work."""

from collections.abc import Collection, Iterable, Sequence

from code_factory.team import rules
from code_factory.team.models import OpenChange
from code_factory.team.service.claims import Claims
from code_factory.team.service.page import Page
from code_factory.team.service.status import Status


class TeamService(Claims, Status, Page):
    """Which agent takes a ticket and why one waits, its claim, what agents do, the page.

    Each async method is one unit of work; times are epoch seconds. Rule helpers other modules
    call are passed through here, so they import this service and nothing below it.
    """

    @staticmethod
    def hold_summary(stage: str, detail: str, missing: Collection[str]) -> str:
        """What a card says holds its ticket: the missing Spec documents, else `detail`."""
        return rules.hold_summary(stage, detail, missing)

    @staticmethod
    def overlap_note(text: str, ticket_id: str, open_changes: Sequence[OpenChange]) -> str | None:
        """Which open change (not the ticket's own) its text likely overlaps, in words."""
        others = [(c.label, c.files) for c in open_changes if c.ticket_id != ticket_id]
        return rules.overlap(rules.named_paths(text), others)

    @staticmethod
    def queue_note(card_overlap: str, reason: str) -> str:
        """The queue's word for a planned ticket: the cap that holds it, else `next, <overlap>`."""
        return rules.queue_note(card_overlap, reason)

    @staticmethod
    def subagent_ticket(calls: Iterable[str], marker: str) -> str | None:
        """The ticket whose worktree the newest tool call (newest first) names."""
        return rules.subagent_ticket(calls, marker)
