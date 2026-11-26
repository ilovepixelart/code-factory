"""The tickets module's public API. Each method is one unit of work in its own session.

`by` names the actor (the owner, a run) and is recorded on the activity a change writes.
"""

from code_factory.tickets.rules import describe, is_outside, merge_entries
from code_factory.tickets.service.activity import ActivityService
from code_factory.tickets.service.common import utc_now
from code_factory.tickets.service.coordinator import CoordinatorService
from code_factory.tickets.service.documents import DocumentService
from code_factory.tickets.service.qa import QaHoldouts
from code_factory.tickets.service.review import ReviewService
from code_factory.tickets.service.tickets import TicketService
from code_factory.tickets.service.unit import TicketUnit

__all__ = [
    "ActivityService",
    "CoordinatorService",
    "DocumentService",
    "QaHoldouts",
    "ReviewService",
    "TicketService",
    "TicketUnit",
    "describe",
    "is_outside",
    "merge_entries",
    "utc_now",
]
