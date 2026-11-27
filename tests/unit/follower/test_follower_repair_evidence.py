from datetime import UTC, datetime

import pytest

from code_factory.delivery.models import PullView
from code_factory.follower.service.repairs import repair_for

NOW = datetime(2026, 11, 27, tzinfo=UTC)


@pytest.mark.parametrize(
    ("pull_fields", "failed", "expected"),
    [
        (None, True, "ci"),
        (None, False, None),
        ({"conflict": True, "ci": "failed"}, True, "conflict"),
        ({"ci": "failed"}, False, "ci"),
        ({"ci": "failed", "other_ci": "none"}, False, None),
        ({"conflict": True, "head": "stale", "ci": "failed"}, False, None),
        ({"conflict": True, "state": "closed"}, False, None),
        ({"ci": "pending"}, False, None),
    ],
)
def test_repairs_require_current_failure_evidence(
    pull_fields: dict[str, object] | None, failed: bool, expected: str | None
) -> None:
    pull = (
        PullView.model_validate(
            {
                "ticket_id": "CF-1",
                "repository": "example",
                "url": "https://example.com/pull/1",
                "since": NOW,
                "read_at": NOW,
                "state": "open",
                "head": "current",
                **pull_fields,
            }
        )
        if pull_fields is not None
        else None
    )

    repair = repair_for("current", pull, check_failed=failed)

    assert (repair.reason if repair else None) == expected
    if repair is not None:
        assert repair.head == "current"
        assert repair.task
