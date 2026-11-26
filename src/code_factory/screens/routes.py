"""Approving a ui ticket's screens, sending them back, and serving a capture's images."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc
from code_factory.screens.service import NO_CAPTURE, NONE_WAITS, ScreensService
from code_factory.tickets.service import TicketService
from code_factory.undo.models import Changed

router = APIRouter(prefix="/api", tags=["inbox"])

ScreensDep = Annotated[ScreensService, Depends(service_of(ScreensService))]
TicketsDep = Annotated[TicketService, Depends(service_of(TicketService))]
OWNER = "owner:owner"
Responses = dict[int | str, dict[str, Any]]
DECIDED: Responses = {404: problem_doc("No such ticket."), 409: problem_doc(f"`{NONE_WAITS}`.")}


class ChangesBody(BaseModel):
    """What should change in the screens."""

    model_config = ConfigDict(extra="forbid", strict=True)

    reason: str


@router.post(
    "/tickets/{repository}/{ticket_id}/screens-approval",
    summary="Approve a ui ticket's screens",
    responses=DECIDED,
)
async def approve(
    repository: str, ticket_id: str, screens: ScreensDep, tickets: TicketsDep
) -> Changed:
    """The waiting capture's tree counts as approved."""
    ticket = (await tickets.locate(repository, ticket_id)).id
    await screens.approve(ticket, by=OWNER)
    return Changed(notice=f"Approved the screens of {ticket}", undo=None)


@router.post(
    "/tickets/{repository}/{ticket_id}/screens-changes",
    summary="Send a ui ticket's screens back",
    responses=DECIDED,
)
async def send_back(
    repository: str, ticket_id: str, body: ChangesBody, screens: ScreensDep, tickets: TicketsDep
) -> Changed:
    """`reason`: what should change; the next run reads it."""
    ticket = (await tickets.locate(repository, ticket_id)).id
    await screens.send_back(ticket, body.reason, by=OWNER)
    return Changed(notice=f"Sent the screens of {ticket} back", undo=None)


@router.get(
    "/captures/{repository}/{ticket_id}/{tree}/{image}",
    summary="A capture's image",
    response_class=FileResponse,
    responses={404: problem_doc(f"`{NO_CAPTURE}`.")},
)
async def image(
    repository: str, ticket_id: str, tree: str, image: str, screens: ScreensDep
) -> FileResponse:
    """An image a recorded capture lists, and nothing outside the captures folder."""
    path = await screens.image(repository, ticket_id, tree, image)
    return FileResponse(path, media_type="image/png")
