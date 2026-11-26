"""Values the memory tests share: the frozen clock and the actor."""

from datetime import UTC, datetime

NOW = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
OWNER = "owner"
