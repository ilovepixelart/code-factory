"""Queue plan writes keep the number of database round trips bounded."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.follower.repository import QueueRepository

NOW = datetime(2026, 11, 27, tzinfo=UTC)


async def test_a_queue_replacement_uses_one_upsert_for_all_changed_notes() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [[(1, "same"), (2, "old"), (3, "gone")], None, None]
    repository = QueueRepository(cast("AsyncSession", session))

    await repository.replace({"CF-1": "same", "CF-2": "", "CF-4": "new"}, NOW)

    _, deletion, upsert = [call.args[0].compile() for call in session.execute.await_args_list]
    assert deletion.params == {"ticket_number_1": [3]}
    assert upsert.params == {
        "ticket_number_m0": 2,
        "note_m0": "",
        "planned_at_m0": NOW,
        "ticket_number_m1": 4,
        "note_m1": "new",
        "planned_at_m1": NOW,
    }
