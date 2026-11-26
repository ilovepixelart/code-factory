"""The run key of a capped run: made once on its first request, held in memory, never a fallback.

A run key is the provider key made with the run's cap as its limit. The row says in which state
the create is (`making` from before the call, `made` once the id is recorded), so a restart or a
second process never makes a second key for the run.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from pydantic import SecretStr

from code_factory.broker.adapters.provider import KeyApi
from code_factory.broker.models import BrokerConnection, TokenGrant
from code_factory.broker.ports import ConnectionSource
from code_factory.broker.repository import BrokerRepository
from code_factory.broker.rules.keys import run_key_request
from code_factory.broker.service.vault import RunKeyVault
from code_factory.platform.db import UnitOfWork

logger = logging.getLogger(__name__)

MAX_REFUSED_CREATES = 3
CLEANUP_S = 5.0


class NoRunKeyError(Exception):
    """No run key can be used for the request; the answer is the fixed 502."""


class RunKeys:
    """Makes and holds the run keys of this process."""

    def __init__(
        self,
        uow: UnitOfWork,
        keys: KeyApi,
        connections: ConnectionSource,
        clock: Callable[[], datetime],
    ) -> None:
        self._uow = uow
        self._keys = keys
        self._connections = connections
        self._clock = clock
        self.vault = RunKeyVault()
        self._locks: dict[str, asyncio.Lock] = {}
        self._refused_creates: dict[str, int] = {}

    def forget(self, run_id: str) -> None:
        """Drop everything held for the run once it has ended."""
        self.vault.drop(run_id)
        self._locks.pop(run_id, None)
        self._refused_creates.pop(run_id, None)

    async def key_for(self, grant: TokenGrant, connection: BrokerConnection) -> SecretStr:
        """The run's key, made on the first call; `NoRunKeyError` when none may be used."""
        if (held := self.vault.get(grant.run_id)) is not None:
            return held
        async with self._locks.setdefault(grant.run_id, asyncio.Lock()):
            if (held := self.vault.get(grant.run_id)) is not None:
                return held
            return await self._make(grant, connection)

    async def _set(
        self, run_id: str, was: tuple[str, ...], now: str, key_id: str | None = None
    ) -> bool:
        async with self._uow() as session:
            return await BrokerRepository(session).set_state(
                run_id, was, now, self._clock(), key_id
            )

    async def _make(self, grant: TokenGrant, connection: BrokerConnection) -> SecretStr:
        run_id = grant.run_id
        if grant.cap_usd is None:
            raise NoRunKeyError
        management = await self._management_key(connection)
        # Only `none` moves to `making`: a refused row, a made key this process no longer holds
        # and a create another process started all lose here, and no second key is made.
        if not await self._set(run_id, ("none",), "making"):
            raise NoRunKeyError
        created = await self._keys.create(
            connection.base_url,
            management,
            run_key_request(run_id, grant.cap_usd, grant.expires_at),
        )
        if not created.answered:
            raise NoRunKeyError  # stays `making`: the sweep refuses it after two minutes
        made = created.made
        if made is None:
            await self._create_refused(run_id)
            raise NoRunKeyError
        if not made.id:
            await self._set(run_id, ("making",), "refused")
            raise NoRunKeyError
        await self._record(run_id, made.id, connection, management)
        self.vault.put(run_id, made.key)
        return made.key

    async def _management_key(self, connection: BrokerConnection) -> SecretStr:
        name = connection.management_key_name
        key = await self._connections.read_key(name) if name is not None else None
        if key is None:
            raise NoRunKeyError
        return key

    async def _create_refused(self, run_id: str) -> None:
        count = self._refused_creates.get(run_id, 0) + 1
        self._refused_creates[run_id] = count
        final = count >= MAX_REFUSED_CREATES
        await self._set(run_id, ("making",), "refused" if final else "none")

    async def _record(
        self, run_id: str, key_id: str, connection: BrokerConnection, management: SecretStr
    ) -> None:
        """Record the id; when that fails delete the key at once rather than lose it."""
        try:
            recorded = await self._set(run_id, ("making",), "made", key_id)
        except Exception:
            logger.exception("a run key was made but its id could not be recorded")
            recorded = False
        if recorded:
            return
        async with asyncio.timeout(CLEANUP_S):
            await asyncio.shield(self._keys.delete(connection.base_url, management, key_id))
        raise NoRunKeyError
