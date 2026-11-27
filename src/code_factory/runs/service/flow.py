"""The flow port over the checks and stages services: what a run's end sets off."""

from code_factory.checks.service import CheckService
from code_factory.platform.errors import ConflictError
from code_factory.platform.services import Services
from code_factory.runs.models import Repair
from code_factory.stages.service import StageService


class FlowAdapter:
    """The checks and stages steps a run's end sets off."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def prepare_build(self, ticket_id: str) -> bool:
        """Seal the requested spec checks before creating an agent claim."""
        return await self._services.get(CheckService).prepare_build(ticket_id)

    async def verify_build(self, ticket_id: str, head: str) -> None:
        """Recheck the receipt against the commit the Build agent will receive."""
        await self._services.get(CheckService).verify_build(ticket_id, head)

    async def admit_repair(self, ticket_id: str, repair: Repair, run_id: str = "") -> None:
        """Refuse a duplicate or an exhausted round, reserving only an actual run."""
        decision = await self._services.get(StageService).begin_fix_round(
            ticket_id, repair.head, repair.reason, run_id=run_id, can_start=bool(run_id)
        )
        if decision.outcome == "halted":
            msg = f"Fix rounds exhausted ({decision.rounds}) on {repair.head[:12]}"
            raise ConflictError(msg)
        if decision.outcome == "given":
            msg = f"A {repair.reason} repair already ran on {repair.head[:12]}"
            raise ConflictError(msg)

    async def release_repair(self, ticket_id: str, run_id: str) -> None:
        """Give back a reservation for which no process could launch."""
        await self._services.get(StageService).release_fix_round(ticket_id, run_id)

    async def build_ended(self, ticket_id: str, head: str) -> None:
        """Queue the head's checks; a ticket the review returned goes back to its evidence."""
        stages = self._services.get(StageService)
        returned_at = await stages.review_return_at(ticket_id)
        await self._services.get(CheckService).queue_head(
            ticket_id, head, review_fix=returned_at is not None
        )
        if returned_at is not None:
            await stages.fix_committed(ticket_id, returned_at=returned_at)

    async def review_ended(self, ticket_id: str, run_id: str, head: str) -> None:
        """Apply the review the run submitted: a pass records it, changes return the ticket."""
        await self._services.get(StageService).apply_review(ticket_id, run_id, head)
