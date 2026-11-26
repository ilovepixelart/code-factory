"""Starting the board's checks on a ticket's head."""

from typing import Annotated

from fastapi import APIRouter, Depends

from code_factory.checks.models import Scope
from code_factory.checks.service import CheckService
from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc
from code_factory.tickets.service import TicketService
from code_factory.undo.models import Changed

router = APIRouter(prefix="/api", tags=["checks"])

ChecksDep = Annotated[CheckService, Depends(service_of(CheckService))]
TicketsDep = Annotated[TicketService, Depends(service_of(TicketService))]


@router.post(
    "/tickets/{repository}/{ticket_id}/checks",
    summary="Run the board's checks on the ticket's branch tip",
    status_code=201,
    responses={
        404: problem_doc("No such ticket."),
        409: problem_doc("No checks command, or checks already running."),
    },
)
async def start_checks(
    repository: str, ticket_id: str, checks: ChecksDep, tickets: TicketsDep
) -> Changed:
    """Queued at once; the ticket's card shows the run."""
    ticket = await tickets.locate(repository, ticket_id)
    await checks.start(str(ticket.id), Scope.REACHED, by="owner:owner")
    return Changed(notice="", undo=None)
