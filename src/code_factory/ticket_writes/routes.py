"""Every ticket write from the board, through the ticket-writes service (stages, undo, refusals)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from code_factory.board.service import BoardService
from code_factory.platform.errors import PreconditionFailedError
from code_factory.platform.web.conditional import still_matches, tag_of
from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import TicketAddress
from code_factory.undo.models import Changed

router = APIRouter(prefix="/api", tags=["tickets"])

WritesDep = Annotated[TicketWriteService, Depends(service_of(TicketWriteService))]
BoardDep = Annotated[BoardService, Depends(service_of(BoardService))]
OWNER = "owner:owner"
Responses = dict[int | str, dict[str, Any]]
REFUSED: Responses = {400: problem_doc("A field does not read, with why.")}
NO_TICKET: Responses = {404: problem_doc("No such ticket.")}
TICKET = "/tickets/{repository}/{ticket_id}"

# A field's value as the app sends it: text; labels and the link lists may also be lists.
Text = str | None
Items = str | list[str] | None
_STRICT = ConfigDict(extra="forbid")


class _Fields(BaseModel):
    """The fields both a new ticket and an edit take; every one optional."""

    model_config = _STRICT

    title: Text = None
    type: Text = None
    description: Text = None
    stage: Text = None
    branch: Text = None
    budget: Text = None
    parallel: Text = None
    tests: Text = None
    e2e: Text = None
    pages: Text = None
    source: Text = None
    parent: Text = None
    blocked_by: Items = None
    caused_by: Items = None
    labels: Items = None
    priority: Text = None
    assignee: Text = None
    due: Text = None
    blocked: Text = None
    archived: Text = None


class CreateBody(_Fields):
    """A new ticket: its repository, and any field a new ticket takes."""

    repository: str


class EditBody(_Fields):
    """An edit: only the fields given change."""

    steps: Text = None


class MoveBody(BaseModel):
    """The column to move to and its order after the move, `repository/id`, top first."""

    model_config = _STRICT

    stage: str
    order: list[str] = []


class LinkBody(BaseModel):
    """`kind` (`parent`, `child`, `blocked_by`, `blocks`) and `target`, the other ticket's id."""

    model_config = _STRICT

    kind: str
    target: str


def _texts(body: BaseModel) -> dict[str, str]:
    """The fields given, each as the text the service reads: lists joined by `, `."""
    return {
        name: ", ".join(value) if isinstance(value, list) else str(value or "")
        for name, value in body.model_dump(exclude_unset=True).items()
    }


def _created(at: TicketAddress) -> JSONResponse:
    """201 with the new ticket's address in `Location` and in the body the app reads."""
    body = {"notice": "", "undo": None, "id": at.id, "repository": at.repository}
    location = f"/api/tickets/{at.repository}/{at.id}"
    return JSONResponse(body, status_code=201, headers={"Location": location})


@router.post("/tickets", summary="Create a ticket", status_code=201, responses=REFUSED)
async def create(body: CreateBody, writes: WritesDep) -> JSONResponse:
    """`repository`, `title` and any field a new ticket takes; a new ticket starts in Spec."""
    fields = _texts(body)
    repository = fields.pop("repository")
    return _created(await writes.create(repository, fields, OWNER))


STALE: Responses = {412: problem_doc("`If-Match` names fields the ticket has changed from.")}


@router.patch(TICKET, summary="Change a ticket's fields", responses=REFUSED | NO_TICKET | STALE)
async def edit(  # noqa: PLR0913, PLR0917  # the path, the body, a header and two services
    repository: str,
    ticket_id: str,
    body: EditBody,
    writes: WritesDep,
    board: BoardDep,
    if_match: Annotated[str | None, Header()] = None,
) -> Changed:
    """Only the fields given change; `archived` is `true` or empty.

    With `If-Match` (the ticket page's `ETag`) the edit applies only while the ticket's fields are
    still the ones read.
    """
    if if_match is not None:
        page = await board.ticket_page(repository, ticket_id)
        if not still_matches(if_match, tag_of(page["ticket"])):
            msg = f"{ticket_id} changed since it was read: read it again and redo the edit"
            raise PreconditionFailedError(msg)
    result = await writes.update(
        TicketAddress(repository=repository, id=ticket_id), _texts(body), OWNER
    )
    return Changed(notice=result.notice, undo=result.undo)


@router.post(
    TICKET + "/move", summary="Move a ticket, with the new order", responses=REFUSED | NO_TICKET
)
async def move(repository: str, ticket_id: str, body: MoveBody, writes: WritesDep) -> Changed:
    """The stage changes, then the column takes the order given."""
    at = TicketAddress(repository=repository, id=ticket_id)
    return await writes.move(at, body.stage, body.order, OWNER)


class BulkBody(BaseModel):
    """`tickets` (`repository/id` each) and exactly one of the actions; `archived: ""` restores."""

    model_config = ConfigDict(extra="forbid", strict=True)

    tickets: list[str]
    stage: str = ""
    priority: str = ""
    label: str = ""
    archived: str = ""


@router.post("/tickets/bulk", summary="One change to several tickets", responses=REFUSED)
async def bulk(body: BulkBody, writes: WritesDep) -> Changed:
    """One change applied to every ticket or to none; one undo takes all of it back."""
    return await writes.bulk_request(body.model_dump(exclude_unset=True), OWNER)


@router.post(TICKET + "/duplicate", summary="Copy a ticket", status_code=201, responses=NO_TICKET)
async def duplicate(repository: str, ticket_id: str, writes: WritesDep) -> JSONResponse:
    """A new ticket titled `(copy)` with the copyable fields; no branch, links or state."""
    return _created(
        await writes.duplicate(TicketAddress(repository=repository, id=ticket_id), OWNER)
    )


@router.post(TICKET + "/links", summary="Link two tickets", responses=REFUSED | NO_TICKET)
async def link(repository: str, ticket_id: str, body: LinkBody, writes: WritesDep) -> Changed:
    """The link is recorded on whichever ticket holds it."""
    at = TicketAddress(repository=repository, id=ticket_id)
    return await writes.add_link(at, body.kind, body.target.strip(), OWNER)


@router.delete(
    TICKET + "/links/{kind}/{target}", summary="Unlink two tickets", responses=REFUSED | NO_TICKET
)
async def unlink(
    repository: str, ticket_id: str, kind: str, target: str, writes: WritesDep
) -> Changed:
    """The link of `kind` to `target`, named in the path: a DELETE carries no body."""
    return await writes.remove_link(
        TicketAddress(repository=repository, id=ticket_id), kind, target, OWNER
    )


@router.delete(
    TICKET,
    summary="Delete a ticket",
    responses=NO_TICKET | {409: problem_doc("An agent runs on it.")},
)
async def delete_ticket(repository: str, ticket_id: str, writes: WritesDep) -> Changed:
    """Hidden from every read; the answer's undo brings it back."""
    return await writes.delete(TicketAddress(repository=repository, id=ticket_id), OWNER)


class LimitBody(BaseModel):
    """The most open tickets the column holds; null clears the limit."""

    model_config = _STRICT

    limit: int | None


@router.put(
    "/columns/{stage}/limit",
    summary="Limit a column's open tickets",
    responses={400: problem_doc("An unknown stage, or a limit that is not a whole number.")},
)
async def column_limit(stage: str, body: LimitBody, writes: WritesDep) -> Changed:
    """`limit` from 1, or null to clear it."""
    return await writes.set_column_limit(stage, body.limit, OWNER)
