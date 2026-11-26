"""A ticket's mock images and its branch's changes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from code_factory.git.service import GitService
from code_factory.platform.errors import NotFoundError
from code_factory.platform.web.dependencies import service_of
from code_factory.tickets.service import DocumentService, TicketService

router = APIRouter(prefix="/api/tickets/{repository}/{ticket_id}", tags=["tickets"])

TicketsDep = Annotated[TicketService, Depends(service_of(TicketService))]
DocumentsDep = Annotated[DocumentService, Depends(service_of(DocumentService))]
GitDep = Annotated[GitService, Depends(service_of(GitService))]
UNKNOWN_REPOSITORY = "unknown repository"


@router.get("/mock/{name}", summary="A mock image of a ticket")
async def mock_file(
    repository: str, ticket_id: str, name: str, tickets: TicketsDep, documents: DocumentsDep
) -> Response:
    """The image, with its own content type."""
    ticket = await tickets.locate(repository, ticket_id)
    image = await documents.get_mock_file(ticket.id, name)
    return Response(image.data, media_type=image.content_type)


@router.get("/diff", summary="The changes on a ticket's branch")
async def diff(repository: str, ticket_id: str, tickets: TicketsDep, git: GitDep) -> dict[str, Any]:
    """The branch against its fork point; empty while the repository or branch is not there."""
    ticket = await tickets.get(ticket_id)
    await tickets.locate(repository, ticket.id)
    try:
        changes = await git.changes(repository, ticket.branch)
    except NotFoundError as unknown:
        if str(unknown) != UNKNOWN_REPOSITORY:
            raise
        return {
            "files": [],
            "cut": False,
            "limit": 400,
            "branch": ticket.branch,
            "default_branch": "",
        }
    return changes.model_dump()
