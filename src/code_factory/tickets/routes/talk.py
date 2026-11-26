"""The owner's side of a ticket's talk and review: comments, messages, answers, findings, undo."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, StrictInt

from code_factory.platform.web.dependencies import service_of
from code_factory.talk.models import Reply
from code_factory.talk.service import TalkService
from code_factory.tickets.service import CoordinatorService, ReviewService, TicketService
from code_factory.undo.models import Changed

router = APIRouter(prefix="/api/tickets/{repository}/{ticket_id}", tags=["tickets"])

TicketsDep = Annotated[TicketService, Depends(service_of(TicketService))]
TalkDep = Annotated[TalkService, Depends(service_of(TalkService))]
ReviewDep = Annotated[ReviewService, Depends(service_of(ReviewService))]
CoordinatorDep = Annotated[CoordinatorService, Depends(service_of(CoordinatorService))]
OWNER = "owner:owner"
NOTHING = {"notice": "", "undo": None}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TextBody(_Strict):
    """What the owner wrote."""

    text: str


class CommentBody(_Strict):
    """The comment, and the changed file and line it is about, if any."""

    text: str
    path: str | None = None
    line: StrictInt | None = None


class AnswerBody(_Strict):
    """The question by its document, index and text; the picked `choices` or a typed `answer`.

    `replace` changes an answer already given on purpose.
    """

    document: str
    index: StrictInt
    question: str
    choices: list[str] = []
    answer: str = ""
    replace: bool = False


class CloseBody(_Strict):
    """`state`, `fixed` or `dismissed`, and the `reason`."""

    state: str
    reason: str = ""


class FieldBody(_Strict):
    """The field to put back."""

    name: str


@router.post("/messages", summary="Leave a message for the agent on a ticket")
async def message(
    repository: str, ticket_id: str, body: TextBody, tickets: TicketsDep, talk: TalkDep
) -> dict[str, Any]:
    """`text`: the running agent gets it at its next step, else the next run starts with it."""
    ticket = await tickets.locate(repository, ticket_id)
    await talk.post_message(ticket.id, body.text, OWNER, "next_run")
    return NOTHING


@router.post("/comments", summary="Comment on a ticket")
async def comment(
    repository: str, ticket_id: str, body: CommentBody, tickets: TicketsDep, talk: TalkDep
) -> dict[str, Any]:
    """`text`, and the `path` and `line` it is about when it comments on a change."""
    ticket = await tickets.locate(repository, ticket_id)
    await talk.add_comment(ticket.id, body.text, OWNER, path=body.path or None, line=body.line)
    return NOTHING


@router.post("/answers", summary="Answer a question an agent asked")
async def answer(
    repository: str, ticket_id: str, body: AnswerBody, tickets: TicketsDep, talk: TalkDep
) -> dict[str, Any]:
    """`document`, `index` and `question` name it; `choices` or `answer` say it; `replace`."""
    ticket = await tickets.locate(repository, ticket_id)
    await talk.answer_shown(
        ticket.id,
        body.document,
        body.index,
        body.question,
        Reply(choices=body.choices, text=body.answer),
        replace=body.replace,
        by=OWNER,
        channel="http",
    )
    return NOTHING


@router.get("/findings", summary="A ticket's review findings")
async def findings(
    repository: str, ticket_id: str, tickets: TicketsDep, reviews: ReviewDep
) -> dict[str, Any]:
    """Each finding and where it stands: blocking ones first, then nits."""
    ticket = await tickets.locate(repository, ticket_id)
    found = await reviews.list_findings(ticket.id)
    return {"findings": [f.model_dump(by_alias=True) for f in found]}


@router.post("/findings/{finding}", summary="Close a finding")
async def close_finding(  # noqa: PLR0913, PLR0917  # the address names three things
    repository: str,
    ticket_id: str,
    finding: str,
    body: CloseBody,
    tickets: TicketsDep,
    reviews: ReviewDep,
) -> dict[str, Any]:
    """`state` (`fixed` or `dismissed`) and the `reason`."""
    ticket = await tickets.locate(repository, ticket_id)
    await reviews.close_finding(ticket.id, finding, body.state, body.reason, by=OWNER)
    return NOTHING


@router.post("/coordinator-undo", summary="Put back a field the coordinator changed")
async def coordinator_undo(
    repository: str,
    ticket_id: str,
    body: FieldBody,
    tickets: TicketsDep,
    coordinator: CoordinatorDep,
) -> Changed:
    """`name`: the field."""
    ticket = await tickets.locate(repository, ticket_id)
    return await coordinator.undo_edit(ticket.id, body.name, by=OWNER)
