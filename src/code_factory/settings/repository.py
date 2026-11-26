"""Queries on `intake_key_grants`."""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from code_factory.platform.db import AsyncSession
from code_factory.settings.models.problems import BoardSettings, IntakeGrant
from code_factory.settings.tables import BoardSetting, IntakeKeyGrant


def _grant(row: IntakeKeyGrant) -> IntakeGrant:
    return IntakeGrant(key_name=row.key_name, repository=row.repository, url=row.url)


class GrantRepository:
    """Queries on `intake_key_grants` over the session of one unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, grant: IntakeGrant) -> IntakeGrant:
        """Store `grant`, replacing an earlier row of that name."""
        values = {"repository": grant.repository, "url": grant.url}
        statement = insert(IntakeKeyGrant).values(key_name=grant.key_name, **values)
        row = await self._session.scalar(
            statement.on_conflict_do_update(
                index_elements=[IntakeKeyGrant.key_name],
                set_={**values, "granted_at": statement.excluded.granted_at},
            ).returning(IntakeKeyGrant)
        )
        assert row is not None  # noqa: S101  # an upsert always returns its row
        return _grant(row)

    async def get(self, key_name: str) -> IntakeGrant | None:
        """The grant of the key, if any."""
        row = await self._session.get(IntakeKeyGrant, key_name)
        return None if row is None else _grant(row)

    async def get_many(self, key_names: list[str]) -> dict[str, IntakeGrant]:
        """The grants of the keys that have one, by name."""
        rows = await self._session.scalars(
            select(IntakeKeyGrant).where(IntakeKeyGrant.key_name.in_(key_names))
        )
        return {row.key_name: _grant(row) for row in rows}

    async def delete(self, key_name: str) -> bool:
        """Delete the grant; whether there was one."""
        deleted = await self._session.scalar(
            delete(IntakeKeyGrant)
            .where(IntakeKeyGrant.key_name == key_name)
            .returning(IntakeKeyGrant.key_name)
        )
        return deleted is not None

    async def list_all(self) -> list[IntakeGrant]:
        """Every grant, ordered by key name."""
        rows = await self._session.scalars(select(IntakeKeyGrant).order_by(IntakeKeyGrant.key_name))
        return [_grant(row) for row in rows]


class BoardSettingsRepository:
    """Queries on `board_settings` over the session of one unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self) -> BoardSettings:
        """Every key that has a row; the others read None."""
        rows = await self._session.scalars(select(BoardSetting))
        return BoardSettings(**{row.key: row.value for row in rows})

    async def write(self, key: str, value: int | None) -> None:
        """Set `key` to `value`, or clear it when `value` is None."""
        if value is None:
            await self._session.execute(delete(BoardSetting).where(BoardSetting.key == key))
            return
        statement = insert(BoardSetting).values(key=key, value=value)
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[BoardSetting.key], set_={"value": statement.excluded.value}
            )
        )
