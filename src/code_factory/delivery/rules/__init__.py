"""Pure rules of delivery: no IO, no clock (`now` is an argument)."""

from code_factory.delivery.rules.merge import (
    HEAD_MOVED,
    NO_SHIPPED,
    NOT_DEFAULT_BASE,
    NOT_READY,
    merge_decision,
    merge_due,
)
from code_factory.delivery.rules.pulls import entered_since, open_match, reduce_pull
from code_factory.delivery.rules.retry import attempts, next_retry, settled, ship_due
from code_factory.delivery.rules.text import (
    behaviour_section,
    feedback_text,
    intake_description,
    issue_of,
    pull_body,
    screens_line,
    status_body,
    ticket_id,
    ticket_number,
    triage,
)

__all__ = [
    "HEAD_MOVED",
    "NOT_DEFAULT_BASE",
    "NOT_READY",
    "NO_SHIPPED",
    "attempts",
    "behaviour_section",
    "entered_since",
    "feedback_text",
    "intake_description",
    "issue_of",
    "merge_decision",
    "merge_due",
    "next_retry",
    "open_match",
    "pull_body",
    "reduce_pull",
    "screens_line",
    "settled",
    "ship_due",
    "status_body",
    "ticket_id",
    "ticket_number",
    "triage",
]
