"""The delivery module's public API: `DeliveryService`."""

from code_factory.delivery.models import PassReport
from code_factory.delivery.ports import Candidate
from code_factory.delivery.service.base import logger
from code_factory.delivery.service.forge import DeliveryForge
from code_factory.delivery.service.intake import IntakeMixin
from code_factory.delivery.service.merging import MergingMixin
from code_factory.delivery.service.reading import ReadingMixin
from code_factory.delivery.service.shipping import ShippingMixin
from code_factory.platform.errors import CodeFactoryError

STEPS = ("record_opened", "ship_finished", "refresh_pulls", "ship_added", "merge_finished")


class DeliveryService(ReadingMixin, ShippingMixin, MergingMixin, IntakeMixin):
    """Pull requests of finished tickets, the board merge, and issue intake."""

    async def run_pass(self, steps: tuple[str, ...] = STEPS) -> PassReport:
        """One pass, steps in their fixed order; a failing step is logged and the rest run."""
        done: dict[str, str] = {}
        candidates = await self._ports.tickets.candidates()
        for step in steps:
            try:
                done[step] = await self._step(step, candidates)
            except CodeFactoryError as error:
                logger.warning("delivery: step %s failed: %s", step, error)
                done[step] = f"failed: {error}"
        return PassReport(steps=done)

    async def _step(self, step: str, candidates: list[Candidate]) -> str:
        if step == "record_opened":
            return f"{await self.record_opened(candidates)} recorded"
        if step == "ship_finished":
            return f"{len(await self._ship_finished(candidates))} shipped"
        if step == "refresh_pulls":
            return f"{await self.refresh_pulls()} read"
        if step == "ship_added":
            return f"{await self._ship_added_all(candidates)} pushed"
        return f"{len(await self.merge_finished())} merged"

    async def _ship_finished(self, candidates: list[Candidate]) -> list[str]:
        shipped: list[str] = []
        for ticket in candidates:
            if ticket.archived or ticket.column not in {"build", "review"} or not ticket.branch:
                continue
            if not (await self._ports.places.switches(ticket.repository)).ship:
                continue
            if (await self.ship(ticket.id)).shipped:
                shipped.append(ticket.id)
        return shipped

    async def _ship_added_all(self, candidates: list[Candidate]) -> int:
        by_id = {ticket.id: ticket for ticket in candidates}
        pushed = 0
        for pull in await self.open_pulls():
            ticket = by_id.get(pull.ticket_id)
            if ticket is not None and await self.ship_added(pull, ticket):
                pushed += 1
        return pushed


__all__ = ["DeliveryForge", "DeliveryService"]
