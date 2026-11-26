"""When a failed remote effect is tried again, and when a ticket's pull request is settled."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from code_factory.delivery.models import DeliveryEvent

DELAYS_S = (5, 15, 45)
TRANSIENT = (
    "connection reset",
    "refused",
    "timed out",
    "could not resolve host",
    "temporary failure in name resolution",
    "i/o timeout",
    "tls handshake timeout",
    "http 502",
    "http 503",
    "http 504",
    "error: 502",
    "error: 503",
    "error: 504",
    "a pull request already exists",
    "http 429",
    "rate limit",
)


def next_retry(attempts: int, reason: str, now: datetime) -> datetime | None:
    """When to try again after `attempts` failures, or `None` when the failure is final."""
    lowered = reason.lower()
    if attempts >= len(DELAYS_S) or not any(marker in lowered for marker in TRANSIENT):
        return None
    return now + timedelta(seconds=DELAYS_S[attempts])


def ship_due(events: Iterable[DeliveryEvent], head: str, now: datetime) -> bool:
    """Whether a ship of `head` may run: every failure of that head has a retry time now past."""
    for event in events:
        if (
            event.kind == "ship_failed"
            and event.head == head
            and (event.retry_at is None or event.retry_at > now)
        ):
            return False
    return True


def attempts(events: Iterable[DeliveryEvent], kind: str, head: str) -> int:
    """How many failures of `kind` name `head`."""
    return sum(1 for e in events if e.kind == kind and e.head == head)


def settled(events: Iterable[DeliveryEvent], url: str, shipped: str) -> bool:
    """Whether the merge of `url` is done: merged, or refused for good at the shipped head."""
    for event in events:
        if event.kind == "merged_pull_request" and event.url == url:
            return True
        if (
            event.kind == "merge_failed"
            and event.url == url
            and event.head == shipped
            and event.retry_at is None
        ):
            return True
    return False
