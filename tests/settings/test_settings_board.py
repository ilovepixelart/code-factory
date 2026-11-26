"""Board-wide settings the follower reads: the overall agent cap and the days a prune keeps."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError
from code_factory.settings.models.problems import BoardSettings
from code_factory.settings.service import SettingsService


@pytest.fixture
def service(uow: UnitOfWork) -> SettingsService:
    return SettingsService(uow)


async def test_a_board_with_nothing_set_has_no_cap_and_no_prune(service: SettingsService) -> None:
    assert await service.board_settings() == BoardSettings(agent_slots=None, prune_days=None)


async def test_a_value_is_stored_and_read_back_beside_the_other_key(
    service: SettingsService,
) -> None:
    assert await service.set_board_setting("agent_slots", 3) == BoardSettings(3, None)
    assert await service.set_board_setting("prune_days", 30) == BoardSettings(3, 30)
    assert await service.board_settings() == BoardSettings(agent_slots=3, prune_days=30)


async def test_a_second_value_replaces_the_first(service: SettingsService) -> None:
    await service.set_board_setting("prune_days", 30)
    assert await service.set_board_setting("prune_days", 7) == BoardSettings(None, 7)


async def test_none_clears_a_key_and_leaves_the_other(service: SettingsService) -> None:
    await service.set_board_setting("agent_slots", 3)
    await service.set_board_setting("prune_days", 30)
    assert await service.set_board_setting("agent_slots", None) == BoardSettings(None, 30)
    assert await service.set_board_setting("agent_slots", None) == BoardSettings(None, 30)


async def test_zero_is_a_value_not_an_absence(service: SettingsService) -> None:
    assert await service.set_board_setting("prune_days", 0) == BoardSettings(None, 0)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("theme", 1, "unknown board setting theme: agent_slots or prune_days"),
        ("agent_slots", -1, "agent_slots is a whole number of 0 or more, not -1"),
        ("prune_days", True, "prune_days is a whole number of 0 or more, not True"),
        ("prune_days", 1.5, "prune_days is a whole number of 0 or more, not 1.5"),
    ],
)
async def test_a_bad_key_or_value_is_refused_and_nothing_is_stored(
    service: SettingsService, key: str, value: object, message: str
) -> None:
    with pytest.raises(BadRequestError) as caught:
        await service.set_board_setting(key, value)  # ty: ignore[invalid-argument-type]
    assert str(caught.value) == message
    assert await service.board_settings() == BoardSettings(None, None)


async def test_the_database_refuses_a_key_outside_the_two(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_board_settings_key"):
        await db_session.execute(
            text("INSERT INTO board_settings (key, value) VALUES ('theme', 1)")
        )


async def test_the_database_refuses_a_negative_value(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_board_settings_value"):
        await db_session.execute(
            text("INSERT INTO board_settings (key, value) VALUES ('prune_days', -1)")
        )
