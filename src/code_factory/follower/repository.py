"""Queries over the follower's table. Every method runs in the session it is given."""

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from code_factory.follower.tables import QueuePlanRow
from code_factory.platform.db.unit_of_work import connection_lost
from code_factory.platform.errors import DatabaseUnavailableError

PREFIX = "CF-"
# One leader per schema: advisory locks are database wide, so the key names the schema.
LOCK_KEY = "hashtextextended(current_schema() || '/code-factory-follower-leader', 0)"


def _number(ticket_id: str) -> int:
    return int(ticket_id.removeprefix(PREFIX))


class QueueRepository:
    """The queue plan."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def plan(self) -> dict[str, str]:
        """Every planned ticket's note."""
        rows = await self._session.scalars(select(QueuePlanRow))
        return {f"{PREFIX}{row.ticket_number}": row.note for row in rows}

    async def replace(self, notes: Mapping[str, str], now: datetime) -> None:
        """Make the plan exactly `notes`: unchanged rows are left, others written or deleted."""
        held = await self.plan()
        gone = [_number(i) for i in held if i not in notes]
        if gone:
            await self._session.execute(
                delete(QueuePlanRow).where(QueuePlanRow.ticket_number.in_(gone))
            )
        for ticket, note in notes.items():
            if held.get(ticket) == note:
                continue
            await self._session.execute(
                pg_insert(QueuePlanRow)
                .values(ticket_number=_number(ticket), note=note, planned_at=now)
                .on_conflict_do_update(
                    index_elements=[QueuePlanRow.ticket_number],
                    set_={"note": note, "planned_at": now},
                )
            )


class Leader:
    """A Postgres session advisory lock held on one connection for the leader's life."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connection: AsyncConnection | None = None

    async def lead(self) -> bool:
        """Whether this process leads now; takes the lock when it is free."""
        try:
            return await self._lead()
        except Exception as error:
            if not (isinstance(error, PoolTimeout) or connection_lost(error)):
                raise
            raise DatabaseUnavailableError("the follower could not reach its database") from error

    async def _lead(self) -> bool:
        connection, self._connection = self._connection, None
        if connection is not None and connection.invalidated:
            await connection.close()
            connection = None
        if connection is None or connection.closed:
            connection = await self._engine.connect()
            statement = f"SELECT pg_try_advisory_lock({LOCK_KEY})"
        else:
            statement = "SELECT 1"
        try:
            took = await connection.scalar(text(statement))
            await connection.commit()
        except BaseException:
            try:
                await connection.invalidate()
            finally:
                await connection.close()
            raise
        if took:
            self._connection = connection
            return True
        await connection.close()
        return False

    async def let_go(self) -> None:
        """Free the lock, then give the connection back.

        A closed connection goes back to the pool still holding a session lock, so the lock is
        released first; a connection that cannot release it is dropped from the pool instead.
        """
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            await connection.scalar(text(f"SELECT pg_advisory_unlock({LOCK_KEY})"))
            await connection.commit()
        except SQLAlchemyError:
            await connection.invalidate()
        await connection.close()
