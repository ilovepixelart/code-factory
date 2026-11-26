"""Queries over the deliveries table. Every method runs in the session it is given."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.memory_extras.models import Delivery, Receipt
from code_factory.memory_extras.tables import MemoryDeliveryRow


class DeliveryRepository:
    """Which entries each run was given."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        run_id: str,
        ticket_id: str,
        repository: str,
        deliveries: Sequence[Delivery],
        at: datetime,
    ) -> None:
        """Store what a run was given; what the run already holds is kept as it is."""
        if not deliveries:
            return
        rows = [
            {
                "run_id": run_id,
                "repository": repository,
                "entry_id": delivery.entry_id,
                "ticket_id": ticket_id,
                "left_out": delivery.left_out,
                "delivered_at": at,
            }
            for delivery in deliveries
        ]
        await self._session.execute(insert(MemoryDeliveryRow).values(rows).on_conflict_do_nothing())

    async def receipts(self, repository: str) -> list[Receipt]:
        """Each run that was given an entry of the repository, oldest first.

        An entry cut by the budget was not given, so it has no receipt.
        """
        rows = await self._session.scalars(
            select(MemoryDeliveryRow)
            .where(
                MemoryDeliveryRow.repository == repository, MemoryDeliveryRow.left_out.is_(False)
            )
            .order_by(
                MemoryDeliveryRow.delivered_at, MemoryDeliveryRow.run_id, MemoryDeliveryRow.entry_id
            )
        )
        return [
            Receipt(entry_id=r.entry_id, run_id=r.run_id, ticket_id=r.ticket_id, at=r.delivered_at)
            for r in rows
        ]

    async def of_run(self, run_id: str) -> list[Delivery]:
        """Everything a run was handed, given or cut, by entry."""
        rows = await self._session.scalars(
            select(MemoryDeliveryRow)
            .where(MemoryDeliveryRow.run_id == run_id)
            .order_by(MemoryDeliveryRow.repository, MemoryDeliveryRow.entry_id)
        )
        return [Delivery(entry_id=r.entry_id, left_out=r.left_out) for r in rows]
