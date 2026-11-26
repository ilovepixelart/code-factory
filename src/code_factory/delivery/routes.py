"""Merging a ticket's pull request from the board."""

from typing import Annotated

from fastapi import APIRouter, Depends

from code_factory.delivery.service import DeliveryService
from code_factory.platform.errors import ConflictError
from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc
from code_factory.tickets.service import TicketService
from code_factory.undo.models import Changed

router = APIRouter(prefix="/api", tags=["delivery"])

DeliveryDep = Annotated[DeliveryService, Depends(service_of(DeliveryService))]
TicketsDep = Annotated[TicketService, Depends(service_of(TicketService))]


@router.post(
    "/tickets/{repository}/{ticket_id}/merge",
    summary="Merge the ticket's pull request at the head the board shipped",
    responses={
        404: problem_doc("No such ticket."),
        409: problem_doc("Not ready to merge, or GitHub refused it, with why."),
    },
)
async def merge(
    repository: str, ticket_id: str, delivery: DeliveryDep, tickets: TicketsDep
) -> Changed:
    """Every guard on the same head; never forced."""
    ticket = await tickets.locate(repository, ticket_id)
    merged = await delivery.merge(str(ticket.id), by="owner:owner")
    return Changed(notice=f"Merged {merged.url}", undo=None)


@router.post(
    "/tickets/{repository}/{ticket_id}/ship",
    summary="Ship the ticket's branch again after a failed ship",
    responses={
        404: problem_doc("No such ticket."),
        409: problem_doc("The ship failed again, or the branch cannot ship, with why."),
    },
)
async def ship(
    repository: str, ticket_id: str, delivery: DeliveryDep, tickets: TicketsDep
) -> Changed:
    """The owner's retry: a recorded failure of the head no longer holds it."""
    ticket = await tickets.locate(repository, ticket_id)
    shipped = await delivery.ship(str(ticket.id), retry=True)
    if not shipped.shipped and not shipped.url:
        msg = f"{ticket.id} did not ship: {shipped.reason}"
        raise ConflictError(msg)
    return Changed(notice=f"Shipped {shipped.url}", undo=None)
