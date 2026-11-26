"""Why an entry waits in the review queue."""

from code_factory.memory_extras.models import Record


def queue_reasons(record: Record, today: str) -> list[str]:
    """The reasons the entry is queued: overdue, the cites that are gone, unused."""
    overdue = not record.proposed and bool(record.review_due) and record.review_due < today
    reasons = ["overdue"] if overdue else []
    if record.stale_cites:
        reasons.append(f"cites gone: {', '.join(record.stale_cites)}")
    if record.unused:
        reasons.append("unused")
    return reasons
