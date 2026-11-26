"""One sweep pass: dead rows, the keys of dead rows at the provider, and creates given up on.

The advisory lock is held only while rows are selected and claimed, never across a provider call;
each claimed row is then deleted with a compare-and-set on its key id.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from code_factory.broker.adapters.provider import KeyApi
from code_factory.broker.models import (
    WHY_ADDRESS,
    WHY_GONE,
    WHY_NO_KEY,
    DeleteResult,
    SweepReport,
    TokenRow,
)
from code_factory.broker.ports import ConnectionSource, RunControl
from code_factory.broker.repository import BrokerRepository
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, NotFoundError

logger = logging.getLogger(__name__)

MAKING_GIVEN_UP = timedelta(minutes=2)
CONTROL_S = 5.0


class Sweeper:
    """Runs the broker's housekeeping; safe to run in two processes at once."""

    def __init__(  # noqa: PLR0913, PLR0917  # the collaborators of one pass
        self,
        uow: UnitOfWork,
        keys: KeyApi,
        connections: ConnectionSource,
        clock: Callable[[], datetime],
        control: Callable[[], RunControl | None],
        call_s: float,
    ) -> None:
        self._uow = uow
        self._keys = keys
        self._connections = connections
        self._clock = clock
        self._control = control
        self._claim_stale = timedelta(seconds=call_s * 2)

    async def sweep(self) -> SweepReport:
        """One pass; an empty report when another process holds the lock."""
        now = self._clock()
        async with self._uow() as session:
            repo = BrokerRepository(session)
            if not await repo.take_sweep_lock():
                return SweepReport()
            dropped = await repo.delete_dead_without_key(now)
            await repo.refuse_stale_making(now - MAKING_GIVEN_UP, now)
            live = await repo.live_run_ids(now)
        gone = await self._gone(live)
        async with self._uow() as session:
            repo = BrokerRepository(session)
            if not await repo.take_sweep_lock():
                return SweepReport(dropped_tokens=dropped)
            await repo.end_runs(gone, now)
            dropped += await repo.delete_dead_without_key(now)
            claimed = await repo.claim_deletes(now, now - self._claim_stale)
        deleted = failed = 0
        for row in claimed:
            if await self._delete_key(row):
                deleted += 1
            else:
                failed += 1
        return SweepReport(deleted=deleted, failed=failed, dropped_tokens=dropped)

    async def _gone(self, live: list[str]) -> list[str]:
        """The live tokens whose run the run control says is not active."""
        control = self._control()
        if control is None or not live:
            return []
        try:
            async with asyncio.timeout(CONTROL_S):
                active = await control.active_run_ids(live)
        except TimeoutError:
            logger.warning("the run control did not answer: no token was ended by the sweep")
            return []
        return [run for run in live if run not in active]

    async def _delete_key(self, row: TokenRow) -> bool:
        result = await self._try_delete(row)
        async with self._uow() as session:
            repo = BrokerRepository(session)
            if result.ok and row.run_key_id is not None:
                return await repo.delete_made(row.id, row.run_key_id)
            await repo.release_failed(row.id, self._clock(), result.why)
        return False

    async def _try_delete(self, row: TokenRow) -> DeleteResult:
        """Delete the run's key at its connection's provider with the management key read now."""
        if row.connection is None or row.run_key_id is None:
            return DeleteResult(ok=False, why=WHY_GONE)
        try:
            connection = await self._connections.get_connection(row.connection)
        except NotFoundError:
            return DeleteResult(ok=False, why=WHY_GONE)
        try:
            self._connections.check_rules(connection)
        except BadRequestError:
            return DeleteResult(ok=False, why=WHY_ADDRESS)
        name = connection.management_key_name
        management = await self._connections.read_key(name) if name is not None else None
        if management is None:
            return DeleteResult(ok=False, why=WHY_NO_KEY)
        return await self._keys.delete(connection.base_url, management, row.run_key_id)
