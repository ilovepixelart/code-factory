"""read_document and write_document."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from code_factory.platform.mcp import current_actor, policy
from code_factory.platform.mcp.hints import READ_ONLY, REPLACES
from code_factory.platform.mcp.scope import TicketRepositories, scope_ticket
from code_factory.platform.services import Services
from code_factory.tickets.models import (
    DocumentName,
    DocumentPage,
    DocumentWrite,
    DocumentWritten,
    WriteMode,
)
from code_factory.tickets.service import DocumentService
from code_factory.tickets.tools.tickets import TicketId

PAGE_CHARS = 20_000
MAX_PAGE_CHARS = 40_000


def register(mcp: FastMCP, services: Services) -> None:
    """Add the document tools to `mcp`."""
    documents = services.get(DocumentService)
    repository_of = services.get(TicketRepositories)

    @mcp.tool(annotations=READ_ONLY)
    async def read_document(
        name: DocumentName,
        ticket_id: TicketId = None,
        offset: Annotated[int, Field(description="Character to start at.", ge=0)] = 0,
        max_chars: Annotated[
            int, Field(description=f"1 to {MAX_PAGE_CHARS}.", ge=1, le=MAX_PAGE_CHARS)
        ] = PAGE_CHARS,
    ) -> DocumentPage:
        """Read one ticket document (requirements, spec, uat, mock, review, notes) as text, a page at a time; next_offset continues it. Use when you need what a document says; get_ticket lists which exist and their versions."""  # noqa: E501
        ticket = await scope_ticket(current_actor(), ticket_id, repository_of)
        return await documents.read_document(ticket, name, offset=offset, max_chars=max_chars)

    @mcp.tool(annotations=REPLACES)
    async def write_document(
        name: DocumentName,
        content: str,
        ticket_id: TicketId = None,
        mode: Annotated[
            WriteMode, Field(description="replace (whole text) or append.")
        ] = "replace",
        base_version: Annotated[
            int | None, Field(description="The version you read; none to create. Not for append.")
        ] = None,
    ) -> DocumentWritten:
        """Replace a document with the whole text (name the version you read, none to create it) or append to it. The text is checked for its kind and refused with the line numbers when wrong. Use to write your stage's output; a run may write only its stage's documents."""  # noqa: E501
        actor = current_actor()
        policy.check_document_write(actor, name.value)
        ticket = await scope_ticket(actor, ticket_id, repository_of)
        write = DocumentWrite(content=content, mode=mode, base_version=base_version)
        return await documents.write_document(ticket, name, write, by=actor.subject)
