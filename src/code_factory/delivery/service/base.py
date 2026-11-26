"""What the delivery service's parts share: the unit of work, the ports, gh and the clock."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from code_factory.delivery.adapters.gh import GhResult, GhRunner
from code_factory.delivery.models import DeliveryEvent, PullReading, PullView
from code_factory.delivery.ports import DeliveryPorts
from code_factory.delivery.repository import DeliveryRepository
from code_factory.delivery.rules import reduce_pull
from code_factory.platform.db import UnitOfWork

logger = logging.getLogger(__name__)

PULL_FIELDS = (
    "url,state,reviewDecision,headRefOid,baseRefName,isDraft,mergeable,mergeStateStatus,"
    "statusCheckRollup,reviews,additions,deletions,changedFiles,createdAt,updatedAt,mergedAt"
)
SHIELD_S = 5.0


def utc_now() -> datetime:
    """Now, in UTC."""
    return datetime.now(UTC)


class Collaborators:
    """The parts of `DeliveryService` read these."""

    def __init__(
        self,
        uow: UnitOfWork,
        ports: DeliveryPorts,
        gh: GhRunner | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow = uow
        self._ports = ports
        self._gh = gh or GhRunner()
        self._clock = clock
        self._merging: dict[str, asyncio.Lock] = {}
        self._owner_holds: dict[str, tuple[str, str]] = {}

    async def _gh_in(self, repository: str, argv: list[str]) -> GhResult:
        return await self._gh.run(await self._ports.places.root(repository), argv)

    async def _gh_json(self, repository: str, argv: list[str]) -> Any:  # noqa: ANN401  # gh's JSON
        return await self._gh.run_json(await self._ports.places.root(repository), argv)

    async def _record(self, event: DeliveryEvent) -> bool:
        """Append an event in its own short transaction, shielded: the effect already happened."""

        async def write() -> bool:
            async with self._uow() as session:
                return await DeliveryRepository(session).record(event)

        return await asyncio.wait_for(asyncio.shield(write()), SHIELD_S)

    async def _pull_of(self, ticket_id: str) -> PullView | None:
        async with self._uow() as session:
            return (await DeliveryRepository(session).pulls([ticket_id])).get(ticket_id)

    async def _events_of(self, ticket_id: str) -> list[DeliveryEvent]:
        async with self._uow() as session:
            return (await DeliveryRepository(session).events([ticket_id])).get(ticket_id, [])

    async def _read_pull(self, ticket_id: str, repository: str, url: str) -> PullView | None:
        """Ask GitHub for the pull request and store what it says."""
        answer = await self._gh_json(repository, ["pr", "view", url, "--json", PULL_FIELDS])
        if not isinstance(answer, dict):
            return None
        return await self.record_reading(ticket_id, repository, url, reduce_pull(answer))

    async def record_reading(
        self,
        ticket_id: str,
        repository: str,
        url: str,
        reading: PullReading,
        *,
        shipped_head: str = "",
    ) -> PullView | None:
        """Store a pull reading and optionally import the commit it was shipped with."""
        async with self._uow() as session:
            repo = DeliveryRepository(session)
            await repo.record_pull(ticket_id, repository, url, reading, self._clock())
            if shipped_head:
                await repo.set_shipped(ticket_id, shipped_head)
        await self._ports.tickets.record_pull(ticket_id, url, reading.state)
        return await self._pull_of(ticket_id)

    async def _open_pulls(self) -> list[PullView]:
        async with self._uow() as session:
            return await DeliveryRepository(session).open_pulls()

    def _event(self, ticket_id: str, kind: str, **fields: object) -> DeliveryEvent:
        values: dict[str, object] = {"ticket_id": ticket_id, "kind": kind, "at": self._clock()}
        return DeliveryEvent.model_validate(values | fields)
