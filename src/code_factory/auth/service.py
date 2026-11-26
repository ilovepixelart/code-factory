"""Issuing, verifying and revoking the tokens callers present to `/mcp` and the owner cookie."""

import asyncio
import logging
import secrets
from collections.abc import AsyncGenerator, Callable, Collection
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import SecretStr

from code_factory.auth import rules
from code_factory.auth.models import (
    BEARER_KINDS,
    Description,
    IssuedToken,
    TokenInfo,
    TokenKind,
)
from code_factory.auth.repository import TokenRepository
from code_factory.auth.tables import AuthToken
from code_factory.platform.db import UnitOfWork
from code_factory.platform.identity import Actor, Role

logger = logging.getLogger(__name__)

NONCE_LIFETIME = timedelta(seconds=60)
SWEEP_GRACE = timedelta(days=1)  # ended tokens stay this long, so a late call can still be told why


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _actor(info: TokenInfo) -> Actor:
    if info.kind is TokenKind.RUN:
        role = Role.RUN if info.ticket_id is not None else Role.COORDINATOR
    else:
        role = Role.OWNER
    return Actor(
        role=role,
        subject=info.subject,
        token_id=info.id,
        run_id=info.run_id,
        ticket_id=info.ticket_id,
        stage=info.stage,
        repository=info.repository,
        expires_at=info.expires_at,
    )


@dataclass(frozen=True)
class _Unit:
    """One transaction's queries and the instant its first statement can run."""

    tokens: TokenRepository
    now: datetime


class AuthService:
    """The one place tokens are made, checked and ended."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        clock: Callable[[], datetime] = _utcnow,
        entropy: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._entropy = entropy

    @asynccontextmanager
    async def _unit(self) -> AsyncGenerator[_Unit]:
        """One transaction: the single place this service reaches the database.

        `now` is read after the connection is held, so a wait for the pool cannot let a token that
        has expired meanwhile pass as live.
        """
        async with self._uow() as session:
            await session.connection()
            yield _Unit(TokenRepository(session), self._clock())

    async def _issue(  # noqa: PLR0913  # the columns of one token
        self,
        unit: _Unit,
        kind: TokenKind,
        lifetime: timedelta,
        *,
        subject: str,
        label: str = "",
        run_id: str | None = None,
        ticket_id: str | None = None,
        stage: str | None = None,
        repository: str | None = None,
    ) -> IssuedToken:
        expires_at = rules.expiry(unit.now, lifetime, kind)
        token = rules.mint(kind, self._entropy(rules.ENTROPY_BYTES))
        stored = await unit.tokens.insert(
            AuthToken(
                kind=kind.value,
                digest=rules.digest(token),
                subject=subject,
                label=label,
                run_id=run_id,
                ticket_id=ticket_id,
                stage=stage,
                repository=repository,
                created_at=unit.now,
                expires_at=expires_at,
            ),
        )
        return IssuedToken(id=stored.id, token=SecretStr(token), expires_at=expires_at)

    async def issue_run_token(  # the identity of one run
        self,
        *,
        run_id: str,
        ticket_id: str | None,
        stage: str,
        repository: str,
        lifetime: timedelta,
    ) -> IssuedToken:
        """A token for one run. Without a ticket it belongs to a coordinator run."""
        async with self._unit() as unit:
            return await self._issue(
                unit,
                TokenKind.RUN,
                lifetime,
                subject=f"run:{run_id}",
                run_id=run_id,
                ticket_id=ticket_id,
                stage=stage,
                repository=repository,
            )

    async def issue_owner_token(self, label: str, *, lifetime: timedelta) -> IssuedToken:
        """The owner's MCP credential; the label names it in lists and in what it writes."""
        rules.check_label(label)
        async with self._unit() as unit:
            return await self._issue(
                unit, TokenKind.OWNER, lifetime, subject=f"owner:{label}", label=label
            )

    async def issue_sign_in_nonce(self, label: str) -> IssuedToken:
        """A one-time value that `redeem_sign_in_nonce` exchanges for a session; 60 seconds."""
        rules.check_label(label)
        async with self._unit() as unit:
            return await self._issue(
                unit, TokenKind.NONCE, NONCE_LIFETIME, subject=f"owner:{label}", label=label
            )

    async def redeem_sign_in_nonce(self, nonce: str, *, lifetime: timedelta) -> IssuedToken | None:
        """Spend a nonce and return the owner session it buys, or `None` for a spent or bad one."""
        if rules.kind_of(nonce) is None:
            return None
        async with self._unit() as unit:
            spent = await unit.tokens.spend_nonce(rules.digest(nonce), unit.now)
            if spent is None:
                return None
            return await self._issue(
                unit, TokenKind.SESSION, lifetime, subject=spent.subject, label=spent.label
            )

    async def verify_token(
        self, token: str, *, kinds: Collection[TokenKind] = BEARER_KINDS
    ) -> Actor | None:
        """The actor a live token of one of `kinds` stands for, else `None`."""
        if rules.kind_of(token) is None:
            return None
        actor_kinds = set(kinds) - {TokenKind.NONCE}  # a nonce is spent, never presented
        async with self._unit() as unit:
            info = await unit.tokens.find_live(rules.digest(token), actor_kinds, unit.now)
            if info is None:
                return None
            await unit.tokens.touch(info.id, unit.now)
            return _actor(info)

    async def is_live(self, token_id: int) -> bool:
        """Whether the token still works: checked before every call of a long-lived stdio server."""
        async with self._unit() as unit:
            return await unit.tokens.is_live(token_id, unit.now)

    async def revoke(self, token_id: int, *, kinds: Collection[TokenKind] | None = None) -> bool:
        """End one token (of `kinds`, any when `None`); `False` when there is none to end."""
        async with self._unit() as unit:
            return await unit.tokens.revoke(token_id, unit.now, kinds)

    async def revoke_run(self, run_id: str) -> int:
        """End every token of a run, when it ends or is stopped; how many were live."""
        async with self._unit() as unit:
            return await unit.tokens.revoke_run(run_id, unit.now)

    async def list_tokens(
        self, *, include_ended: bool = False, kinds: Collection[TokenKind] | None = None
    ) -> list[TokenInfo]:
        """Stored tokens (of `kinds`, any when `None`) without their values, oldest first."""
        async with self._unit() as unit:
            return await unit.tokens.list_tokens(unit.now, include_ended=include_ended, kinds=kinds)

    async def sweep_expired(self) -> int:
        """Delete tokens that ended more than a day ago; how many."""
        async with self._unit() as unit:
            return await unit.tokens.delete_ended_before(unit.now - SWEEP_GRACE)

    @staticmethod
    def describe(actor: Actor) -> Description:
        """What the actor is, as `whoami` reports it."""
        return Description(
            role=actor.role,
            subject=actor.subject,
            run_id=actor.run_id,
            ticket_id=actor.ticket_id,
            stage=actor.stage,
            repository=actor.repository,
            expires_at=actor.expires_at,
        )


class _Sweeper(Protocol):
    async def sweep_expired(self) -> int: ...


async def sweep_forever(auth: _Sweeper, *, interval_s: float) -> None:
    """Delete ended tokens every `interval_s` seconds until cancelled.

    The first pass comes one interval in. A pass that fails is logged and the next one runs;
    cancellation is never swallowed.
    """
    while True:
        await asyncio.sleep(interval_s)
        try:
            await auth.sweep_expired()
        except Exception:
            logger.exception("token sweep failed")
