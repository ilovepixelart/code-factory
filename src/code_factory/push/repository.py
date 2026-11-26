"""Queries on the push module's tables."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.push.models import Kept, Target
from code_factory.push.tables import PushFailureRow, PushSentRow, PushTargetRow, ReplyTokenRow

_ONE = 1


class PushRepository:
    """The target, the sent digests, the failure and the reply tokens, in one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def target(self) -> Target | None:
        """The target set, if any."""
        row = await self._session.get(PushTargetRow, _ONE)
        return None if row is None else Target(format=row.format, url=row.url)  # ty: ignore[invalid-argument-type]  # the table's check holds the format

    async def set_target(self, target: Target, now: datetime) -> None:
        """Set the one target."""
        values = {"id": _ONE, "format": target.format, "url": target.url, "set_at": now}
        await self._session.execute(
            insert(PushTargetRow)
            .values(values)
            .on_conflict_do_update(index_elements=["id"], set_=values)
        )

    async def clear_target(self) -> None:
        """Remove the target, what was sent and the failure."""
        await self._session.execute(delete(PushTargetRow))
        await self._session.execute(delete(PushSentRow))
        await self._session.execute(delete(PushFailureRow))

    async def failure(self) -> tuple[datetime, str] | None:
        """The last failure: when and the problem."""
        row = await self._session.get(PushFailureRow, _ONE)
        return None if row is None else (row.at, row.problem)

    async def set_failure(self, at: datetime, problem: str) -> None:
        """Record the failure of a pass."""
        values = {"id": _ONE, "at": at, "problem": problem}
        await self._session.execute(
            insert(PushFailureRow)
            .values(values)
            .on_conflict_do_update(index_elements=["id"], set_=values)
        )

    async def clear_failure(self) -> None:
        """Forget the failure: a pass failed nothing."""
        await self._session.execute(delete(PushFailureRow))

    async def keep_only_sent(self, waiting: set[str]) -> set[str]:
        """Forget digests of items that no longer wait; the digests still sent."""
        await self._session.execute(delete(PushSentRow).where(PushSentRow.digest.not_in(waiting)))
        return set(await self._session.scalars(select(PushSentRow.digest)))

    async def claim(self, digest: str, now: datetime) -> bool:
        """Record `digest` as sent unless a pass already did; whether this call recorded it."""
        taken = await self._session.scalar(
            insert(PushSentRow)
            .values(digest=digest, sent_at=now)
            .on_conflict_do_nothing()
            .returning(PushSentRow.digest)
        )
        return taken is not None

    async def unclaim(self, digest: str) -> None:
        """Take back a claim whose delivery failed, so the next pass sends it."""
        await self._session.execute(delete(PushSentRow).where(PushSentRow.digest == digest))

    async def mint(self, digest: str, kept: Kept, now: datetime) -> None:
        """Keep a token, replacing any earlier one of the same request or question."""
        same = (
            ReplyTokenRow.request == kept.request
            if kept.request
            else ReplyTokenRow.question == list(kept.question)
        )
        await self._session.execute(delete(ReplyTokenRow).where(same))
        self._session.add(
            ReplyTokenRow(
                digest=digest, request=kept.request, question=list(kept.question), minted_at=now
            )
        )

    async def find(self, digest: str) -> Kept | None:
        """The token kept under `digest`, if any."""
        row = await self._session.get(ReplyTokenRow, digest)
        if row is None:
            return None
        return Kept(row.request, tuple(row.question), row.minted_at.timestamp())

    async def spend(self, digest: str) -> Kept | None:
        """Take the token out: it answers once, whatever happens next."""
        row = await self._session.scalar(
            delete(ReplyTokenRow).where(ReplyTokenRow.digest == digest).returning(ReplyTokenRow)
        )
        if row is None:
            return None
        return Kept(row.request, tuple(row.question), row.minted_at.timestamp())

    async def forget_before(self, before: datetime) -> None:
        """Drop tokens minted before `before`: no wait lasts that long."""
        await self._session.execute(delete(ReplyTokenRow).where(ReplyTokenRow.minted_at < before))
