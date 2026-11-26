"""Queries over the remote runners' offers, claims and declines."""

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.checks.rules import CLAIM_HOLDS, DECLINE_LIVE, OFFER_LIVE
from code_factory.checks.tables import CheckClaimRow, CheckDeclineRow, CheckOfferRow


class RemoteStore:
    """Offers, claims and declines."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def offer(self, runner: str, repositories: list[str], now: datetime) -> None:
        """Record that `runner` asks for checks of `repositories`; stale offers are dropped."""
        await self._session.execute(
            delete(CheckOfferRow).where(CheckOfferRow.offered_at <= now - OFFER_LIVE)
        )
        statement = insert(CheckOfferRow).values(
            runner=runner, repositories=repositories, offered_at=now
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["runner"],
                set_={"repositories": repositories, "offered_at": now},
            )
        )

    async def sweep(self, now: datetime) -> None:
        """Delete offers older than 600 s and declines older than a day."""
        await self._session.execute(
            delete(CheckOfferRow).where(CheckOfferRow.offered_at <= now - OFFER_LIVE)
        )
        await self._session.execute(
            delete(CheckDeclineRow).where(CheckDeclineRow.declined_at <= now - DECLINE_LIVE)
        )

    async def offered(self, repository: str, now: datetime) -> bool:
        """Whether a runner offered for `repository` within 600 s."""
        statement = select(CheckOfferRow.runner).where(
            CheckOfferRow.offered_at > now - OFFER_LIVE,
            CheckOfferRow.repositories.contains([repository]),
        )
        return (await self._session.execute(statement.limit(1))).first() is not None

    async def decline(self, repository: str, subject: str, head: str, now: datetime) -> None:
        """Record that a runner gave the head back; old declines are dropped."""
        await self._session.execute(
            delete(CheckDeclineRow).where(CheckDeclineRow.declined_at <= now - DECLINE_LIVE)
        )
        statement = insert(CheckDeclineRow).values(
            repository=repository, subject=subject, head=head, declined_at=now
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["repository", "subject", "head"], set_={"declined_at": now}
            )
        )

    async def declined(self, repository: str, subject: str, head: str, now: datetime) -> bool:
        """Whether the head was given back within a day."""
        statement = select(CheckDeclineRow.head).where(
            CheckDeclineRow.repository == repository,
            CheckDeclineRow.subject == subject,
            CheckDeclineRow.head == head,
            CheckDeclineRow.declined_at > now - DECLINE_LIVE,
        )
        return (await self._session.execute(statement)).first() is not None

    async def claim(
        self, repository: str, subject: str, head: str, holder: str, now: datetime
    ) -> bool:
        """Take the claim on a head: free, lapsed (unbeaten for 60 s) or already `holder`'s."""
        statement = insert(CheckClaimRow).values(
            repository=repository,
            subject=subject,
            head=head,
            holder=holder,
            claimed_at=now,
            beat_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["repository", "subject", "head"],
            set_={"holder": holder, "claimed_at": now, "beat_at": now},
            where=(CheckClaimRow.beat_at <= now - CLAIM_HOLDS) | (CheckClaimRow.holder == holder),
        ).returning(CheckClaimRow.id)
        return (await self._session.execute(statement)).first() is not None

    async def beat(
        self, repository: str, subject: str, head: str, holder: str, now: datetime
    ) -> bool:
        """Keep the claim `holder` holds; False when it does not hold it or it lapsed."""
        statement = (
            update(CheckClaimRow)
            .where(
                CheckClaimRow.repository == repository,
                CheckClaimRow.subject == subject,
                CheckClaimRow.head == head,
                CheckClaimRow.holder == holder,
                CheckClaimRow.beat_at > now - CLAIM_HOLDS,
            )
            .values(beat_at=now)
            .returning(CheckClaimRow.id)
        )
        return (await self._session.execute(statement)).first() is not None

    async def release(
        self, repository: str, subject: str, head: str, holder: str, now: datetime
    ) -> bool:
        """Give up a live claim `holder` holds; False when it did not hold one."""
        statement = (
            delete(CheckClaimRow)
            .where(
                CheckClaimRow.repository == repository,
                CheckClaimRow.subject == subject,
                CheckClaimRow.head == head,
                CheckClaimRow.holder == holder,
                CheckClaimRow.beat_at > now - CLAIM_HOLDS,
            )
            .returning(CheckClaimRow.id)
        )
        return (await self._session.execute(statement)).first() is not None

    async def claimed(self, repository: str, subject: str, head: str, now: datetime) -> bool:
        """Whether a live claim holds the head."""
        statement = select(CheckClaimRow.id).where(
            CheckClaimRow.repository == repository,
            CheckClaimRow.subject == subject,
            CheckClaimRow.head == head,
            CheckClaimRow.beat_at > now - CLAIM_HOLDS,
        )
        return (await self._session.execute(statement)).first() is not None
