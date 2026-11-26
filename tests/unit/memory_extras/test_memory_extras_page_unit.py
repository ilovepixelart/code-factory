"""The Memory page over real memory rows: lists, History, left-out, queue and delivery counts."""

from code_factory.memory_extras.models import Record

RECORD_KEYS = [
    "id", "kind", "date", "source", "statement", "why", "guard", "repository", "reviewed",
    "guard_state", "loaded", "left_out", "superseded_by", "scope", "supersedes", "loads", "chars",
    "proposed", "stale", "incomplete", "review_due", "filing", "cites", "stale_cites",
    "received_by", "received_count", "last_received", "unused",
]  # fmt: skip


def test_the_record_type_lists_its_keys_in_the_previous_order() -> None:
    assert list(Record.model_fields) == RECORD_KEYS
