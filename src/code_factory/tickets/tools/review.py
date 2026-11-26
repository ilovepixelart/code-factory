"""submit_review and dismiss_finding."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from code_factory.platform.mcp import current_actor
from code_factory.platform.mcp.hints import APPENDS, REPLACES
from code_factory.platform.mcp.scope import TicketRepositories, scope_ticket
from code_factory.platform.services import Services
from code_factory.tickets.models import (
    Finding,
    FindingDismissed,
    Review,
    ReviewSubmitted,
    Verdict,
)
from code_factory.tickets.service import ReviewService
from code_factory.tickets.tools.tickets import TicketId


def register(mcp: FastMCP, services: Services) -> None:
    """Add the review tools to `mcp`."""
    reviews = services.get(ReviewService)
    repository_of = services.get(TicketRepositories)

    @mcp.tool(annotations=REPLACES)
    async def submit_review(
        verdict: Verdict,
        summary: Annotated[str, Field(description="At most 1000 characters.")],
        findings: Annotated[
            list[Finding] | None,
            Field(description="One per requirement missing, untested or wrong."),
        ] = None,
        ticket_id: TicketId = None,
    ) -> ReviewSubmitted:
        """Submit your review of this ticket's branch: a verdict and one finding per requirement that is missing, untested or wrong. A changes verdict needs a finding and a pass has none; a finding that continues an earlier one names it in prior_id. Use once, when the review is done."""  # noqa: E501
        actor = current_actor()
        ticket = await scope_ticket(actor, ticket_id, repository_of)
        review = Review(verdict=verdict, summary=summary, findings=findings or [])
        return await reviews.submit_review(ticket, review, by=actor.subject)

    @mcp.tool(annotations=APPENDS)
    async def dismiss_finding(
        finding_id: Annotated[str, Field(description="A finding id such as F2.")],
        reason: Annotated[str, Field(description="Why it does not apply, 1 to 1000 characters.")],
        ticket_id: TicketId = None,
    ) -> FindingDismissed:
        """Dismiss a review finding you do not agree with, with the reason; the reviewer and the owner read it on the ticket. Use when a finding is wrong or out of scope; to fix one, change the code instead. A finding is dismissed once."""  # noqa: E501
        actor = current_actor()
        ticket = await scope_ticket(actor, ticket_id, repository_of)
        return await reviews.dismiss_finding(ticket, finding_id, reason, by=actor.subject)
