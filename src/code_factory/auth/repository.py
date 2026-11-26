"""Queries on `auth_tokens`."""

from collections.abc import Collection
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, delete, func, select, true, update

from code_factory.auth.models import TokenInfo, TokenKind
from code_factory.auth.tables import AuthToken
from code_factory.platform.db import AsyncSession

LAST_USE_RESOLUTION = timedelta(minutes=1)


def _info(row: AuthToken) -> TokenInfo:
    return TokenInfo(
        id=row.id,
        kind=TokenKind(row.kind),
        subject=row.subject,
        label=row.label,
        run_id=row.run_id,
        ticket_id=row.ticket_id,
        stage=row.stage,
        repository=row.repository,
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        last_used_at=row.last_used_at,
    )


def _of(kinds: Collection[TokenKind] | None) -> ColumnElement[bool]:
    if kinds is None:
        return true()
    return AuthToken.kind.in_([kind.value for kind in kinds])


class TokenRepository:
    """Queries on `auth_tokens` over the session of one unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, token: AuthToken) -> TokenInfo:
        """Store `token` and return what was stored."""
        self._session.add(token)
        await self._session.flush()
        return _info(token)

    async def find_live(
        self, digest: str, kinds: Collection[TokenKind], now: datetime
    ) -> TokenInfo | None:
        """The token with this digest when it is of one of `kinds`, not revoked and not expired."""
        row = await self._session.scalar(
            select(AuthToken).where(
                AuthToken.digest == digest,
                AuthToken.kind.in_([kind.value for kind in kinds]),
                AuthToken.revoked_at.is_(None),
                AuthToken.expires_at > now,
            )
        )
        return None if row is None else _info(row)

    async def touch(self, token_id: int, now: datetime) -> None:
        """Record a use, at most once per `LAST_USE_RESOLUTION`: reads do not write every call."""
        await self._session.execute(
            update(AuthToken)
            .where(
                AuthToken.id == token_id,
                (AuthToken.last_used_at.is_(None))
                | (AuthToken.last_used_at <= now - LAST_USE_RESOLUTION),
            )
            .values(last_used_at=now)
        )

    async def is_live(self, token_id: int, now: datetime) -> bool:
        """Whether the token exists, is not revoked and has not expired."""
        found = await self._session.scalar(
            select(AuthToken.id).where(
                AuthToken.id == token_id, AuthToken.revoked_at.is_(None), AuthToken.expires_at > now
            )
        )
        return found is not None

    async def revoke(
        self, token_id: int, now: datetime, kinds: Collection[TokenKind] | None
    ) -> bool:
        """Revoke one token of `kinds` (any when `None`); `False` when there is none to revoke."""
        revoked = await self._session.scalar(
            update(AuthToken)
            .where(AuthToken.id == token_id, AuthToken.revoked_at.is_(None), _of(kinds))
            .values(revoked_at=now)
            .returning(AuthToken.id)
        )
        return revoked is not None

    async def revoke_run(self, run_id: str, now: datetime) -> int:
        """Revoke every token of the run that is still live; how many."""
        revoked = await self._session.scalars(
            update(AuthToken)
            .where(
                AuthToken.run_id == run_id,
                AuthToken.revoked_at.is_(None),
                AuthToken.expires_at > now,
            )
            .values(revoked_at=now)
            .returning(AuthToken.id)
        )
        return len(revoked.all())

    async def spend_nonce(self, digest: str, now: datetime) -> TokenInfo | None:
        """Revoke a live nonce and return it, in one statement, so two redeemers cannot both win."""
        row = await self._session.scalar(
            update(AuthToken)
            .where(
                AuthToken.digest == digest,
                AuthToken.kind == TokenKind.NONCE.value,
                AuthToken.revoked_at.is_(None),
                AuthToken.expires_at > now,
            )
            .values(revoked_at=now)
            .returning(AuthToken)
        )
        return None if row is None else _info(row)

    async def list_tokens(
        self, now: datetime, *, include_ended: bool, kinds: Collection[TokenKind] | None
    ) -> list[TokenInfo]:
        """Tokens of `kinds` (any when `None`) oldest first; by default only those still working."""
        query = select(AuthToken).where(_of(kinds)).order_by(AuthToken.id)
        if not include_ended:
            query = query.where(AuthToken.revoked_at.is_(None), AuthToken.expires_at > now)
        return [_info(row) for row in await self._session.scalars(query)]

    async def delete_ended_before(self, cutoff: datetime) -> int:
        """Delete tokens that stopped working before `cutoff`; how many."""
        ended = func.least(
            AuthToken.expires_at, func.coalesce(AuthToken.revoked_at, AuthToken.expires_at)
        )
        deleted = await self._session.scalars(
            delete(AuthToken).where(ended < cutoff).returning(AuthToken.id)
        )
        return len(deleted.all())
