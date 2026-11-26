"""Queries over `broker_tokens`. Every state change is a compare-and-set on the row."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.broker.models import TokenRow
from code_factory.broker.tables import BrokerTokenRow

# The sweep's advisory lock, one per schema: locks are database wide, so the key names the schema.
SWEEP_LOCK = "hashtextextended(current_schema() || '/code-factory-broker-sweep', 0)"
_T = BrokerTokenRow
_NO_KEY = ("none", "refused")


def _row(row: BrokerTokenRow) -> TokenRow:
    return TokenRow.model_validate(row, from_attributes=True)


def _dead(now: datetime) -> ColumnElement[bool]:
    return or_(_T.ended_at.is_not(None), _T.expires_at <= now)


class BrokerRepository:
    """Reads and writes the broker's rows inside the caller's unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(  # noqa: PLR0913, PLR0917  # one row's columns
        self,
        digest: str,
        run_id: str,
        connection: str | None,
        cap_usd: Decimal | None,
        created_at: datetime,
        expires_at: datetime,
    ) -> bool:
        """Insert the run's row; `False` when the run already holds one."""
        added = await self._session.scalar(
            insert(_T)
            .values(
                digest=digest,
                run_id=run_id,
                connection=connection,
                cap_usd=cap_usd,
                created_at=created_at,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(index_elements=["run_id"])
            .returning(_T.id)
        )
        return added is not None

    async def by_digest(self, digest: str) -> TokenRow | None:
        """The row of the token with this digest."""
        found = await self._session.scalar(select(_T).where(_T.digest == digest))
        return None if found is None else _row(found)

    async def by_run(self, run_id: str) -> TokenRow | None:
        """The run's row."""
        found = await self._session.scalar(select(_T).where(_T.run_id == run_id))
        return None if found is None else _row(found)

    async def end(self, run_id: str, at: datetime) -> TokenRow | None:
        """Mark the run's token ended (the first end wins); the row, `None` when unknown."""
        await self._session.execute(
            update(_T).where(_T.run_id == run_id, _T.ended_at.is_(None)).values(ended_at=at)
        )
        return await self.by_run(run_id)

    async def delete_without_key(self, run_id: str) -> bool:
        """Delete the run's row when no key was ever recorded for it."""
        gone = await self._session.scalar(
            delete(_T).where(_T.run_id == run_id, _T.key_state.in_(_NO_KEY)).returning(_T.id)
        )
        return gone is not None

    async def set_state(  # a compare-and-set names both ends of the move
        self,
        run_id: str,
        was: tuple[str, ...],
        now: str,
        at: datetime,
        key_id: str | None = None,
    ) -> bool:
        """Move the run's key state from one of `was` to `now`; `False` when it was not there."""
        moved = await self._session.scalar(
            update(_T)
            .where(_T.run_id == run_id, _T.key_state.in_(was))
            .values(key_state=now, key_state_at=at, run_key_id=key_id)
            .returning(_T.id)
        )
        return moved is not None

    async def take_sweep_lock(self) -> bool:
        """Take the sweep's advisory lock until the transaction ends; `False` when held."""
        taken = await self._session.scalar(text(f"select pg_try_advisory_xact_lock({SWEEP_LOCK})"))
        return bool(taken)

    async def delete_dead_without_key(self, now: datetime) -> int:
        """Delete rows that ended or expired and hold no key."""
        gone = await self._session.scalars(
            delete(_T).where(_dead(now), _T.key_state.in_(_NO_KEY)).returning(_T.id)
        )
        return len(gone.all())

    async def live_run_ids(self, now: datetime) -> list[str]:
        """The runs whose token is neither ended nor expired."""
        found = await self._session.scalars(
            select(_T.run_id).where(_T.ended_at.is_(None), _T.expires_at > now)
        )
        return list(found)

    async def end_runs(self, run_ids: list[str], at: datetime) -> int:
        """End the tokens of these runs; how many were still live."""
        ended = await self._session.scalars(
            update(_T)
            .where(_T.run_id.in_(run_ids), _T.ended_at.is_(None))
            .values(ended_at=at)
            .returning(_T.id)
        )
        return len(ended.all())

    async def claim_deletes(self, now: datetime, stale: datetime) -> list[TokenRow]:
        """Take the dead rows that hold a key, for one sweep to delete.

        A claim older than `stale` is taken again: its sweep died.
        """
        claimed = await self._session.scalars(
            update(_T)
            .where(
                _dead(now),
                _T.key_state == "made",
                or_(_T.delete_claimed_at.is_(None), _T.delete_claimed_at < stale),
            )
            .values(delete_claimed_at=now)
            .returning(_T)
        )
        return [_row(row) for row in claimed.all()]

    async def delete_made(self, row_id: int, key_id: str) -> bool:
        """Delete the row whose key the provider confirmed gone."""
        gone = await self._session.scalar(
            delete(_T)
            .where(_T.id == row_id, _T.key_state == "made", _T.run_key_id == key_id)
            .returning(_T.id)
        )
        return gone is not None

    async def release_failed(self, row_id: int, at: datetime, why: str) -> None:
        """Keep the row after a failed delete: the sentence, the time, and the claim given up."""
        await self._session.execute(
            update(_T)
            .where(_T.id == row_id)
            .values(delete_claimed_at=None, key_delete_failed_at=at, key_delete_error=why)
        )

    async def refuse_stale_making(self, before: datetime, at: datetime) -> int:
        """Rows whose create started before `before` and never recorded: no key for them."""
        moved = await self._session.scalars(
            update(_T)
            .where(_T.key_state == "making", _T.key_state_at < before)
            .values(key_state="refused", key_state_at=at)
            .returning(_T.id)
        )
        return len(moved.all())

    async def counts(self, now: datetime) -> tuple[int, int, int]:
        """Live tokens, rows holding a made key, rows whose key is waiting to be deleted."""
        live = _T.ended_at.is_(None) & (_T.expires_at > now)
        pending = and_(_dead(now), _T.key_state.in_(("making", "made")))
        query = select(
            func.count().filter(live),
            func.count().filter(_T.key_state == "made"),
            func.count().filter(pending),
        )
        live_n, held, waiting = (await self._session.execute(query)).one()
        return live_n, held, waiting

    async def listed(self, now: datetime) -> list[TokenRow]:
        """Live rows and rows waiting for their key's delete, oldest first."""
        wanted = or_(
            and_(_T.ended_at.is_(None), _T.expires_at > now),
            and_(_dead(now), _T.key_state.in_(("making", "made"))),
        )
        rows = await self._session.scalars(select(_T).where(wanted).order_by(_T.id))
        return [_row(row) for row in rows]
