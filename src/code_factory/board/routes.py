"""The board, the ticket page, the filtered ticket list, the archive and the repository list."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict

from code_factory.board.service import BoardService
from code_factory.platform.web.conditional import matches, tag_of
from code_factory.platform.web.dependencies import service_of

router = APIRouter(prefix="/api", tags=["board"])

BoardDep = Annotated[BoardService, Depends(service_of(BoardService))]


@router.get("/board", summary="Every open ticket by column")
async def board(request: Request, service: BoardDep) -> Response:
    """The board, ETag'd: an unchanged board answers 304 to its own tag."""
    answer = await service.board()
    headers = {"ETag": answer.etag, "Cache-Control": "no-cache"}
    if matches(request.headers.get("if-none-match"), answer.etag):
        return Response(status_code=304, headers=headers)
    return Response(answer.body, media_type="application/json", headers=headers)


@router.get("/tickets", summary="The open tickets that match the filters, by column")
async def tickets(request: Request, service: BoardDep) -> JSONResponse:
    """Filters: type, priority, label, assignee, repository (repeatable), blocked, agent, ..."""
    filters: dict[str, list[str]] = {}
    for name, value in request.query_params.multi_items():
        filters.setdefault(name, []).append(value)
    return JSONResponse(await service.tickets(filters))


@router.get("/tickets/{repository}/{ticket_id}", summary="One ticket's page")
async def ticket_page(repository: str, ticket_id: str, service: BoardDep) -> JSONResponse:
    """Fields, documents rendered, links, activity and the card.

    `ETag` tags the `ticket` fields alone, for an edit's `If-Match`: the rest of the page holds
    times measured against the clock, so no tag of the whole page outlives a second.
    """
    page = await service.ticket_page(repository, ticket_id)
    return JSONResponse(page, headers={"ETag": tag_of(page["ticket"])})


@router.get("/repositories", summary="The repositories tickets are filed in")
async def repositories(service: BoardDep) -> list[str]:
    """Names in order."""
    return await service.repositories()


@router.get("/repositories/{repository}/templates/{kind}", summary="A new ticket's starting text")
async def template(repository: str, kind: str, service: BoardDep) -> dict[str, str]:
    """The text a ticket of this type starts with."""
    return await service.template(repository, kind)


@router.get("/archive", summary="Archived tickets")
async def archive(  # noqa: PLR0913, PLR0917  # one parameter per query field
    service: BoardDep,
    q: str = "",
    sort: str = "",
    dir: str = "",  # noqa: A002  # the address's name for the order
    show: str = "",
    page: str | None = None,
    size: str | None = None,
) -> JSONResponse:
    """Rows matching `q` (id or title), of kind `show`, by `sort` and `dir`, paged.

    An unknown `sort` falls back to newest first and the answer names the order applied.
    """
    asked = {"q": q, "sort": sort, "dir": dir, "show": show, "page": page, "size": size}
    query = {key: value for key, value in asked.items() if value is not None}
    return JSONResponse(await service.archive(query))


@router.get("/views", summary="Saved board views")
async def list_views(service: BoardDep) -> list[dict[str, str]]:
    """Each view's name and the address query it applies, in the order saved."""
    return await service.list_views()


class ViewBody(BaseModel):
    """A view: its name and the address query it applies."""

    model_config = ConfigDict(extra="forbid")

    name: str
    query: str


@router.post("/views", summary="Save the board's filters under a name")
async def save_view(body: ViewBody, service: BoardDep) -> dict[str, Any]:
    """`name` and `query`; a name already saved is a 409."""
    await service.save_view(body.name, body.query)
    return {}


@router.delete("/views/{name}", summary="Delete a saved view")
async def delete_view(name: str, service: BoardDep) -> dict[str, Any]:
    """The view named in the path: a DELETE carries no body."""
    await service.delete_view(name)
    return {}
