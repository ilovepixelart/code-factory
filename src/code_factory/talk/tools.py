"""The question tools: a run asks the owner, the owner answers, both read what is open."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from code_factory.platform.identity import Role
from code_factory.platform.mcp import current_actor
from code_factory.platform.mcp.hints import APPENDS, READ_ONLY, REPLACES
from code_factory.platform.mcp.results import PageLimit
from code_factory.platform.mcp.scope import TicketRepositories, scope_ticket
from code_factory.platform.services import Services
from code_factory.talk.models import (
    Answered,
    Choice,
    QuestionAsked,
    QuestionFilter,
    QuestionPage,
    Reply,
    StatusFilter,
)
from code_factory.talk.rules import CHOICES_MAX, CHOICES_MIN, QUESTION_LIMIT, TOPIC_LIMIT
from code_factory.talk.service import TalkService

TicketId = Annotated[
    str | None,
    Field(description="The ticket, such as CF-12. A run may leave it out: it has one ticket."),
]


class ChoiceOffered(BaseModel):
    """A choice a question offers: a short label, what it means, and an optional preview."""

    text: Annotated[str, Field(description="A short label, a few words.")]
    description: Annotated[
        str, Field(description="What picking it means or its trade-off, in a sentence or two.")
    ] = ""
    recommended: Annotated[
        bool,
        Field(description="The one you would pick; it is shown first. Say why in its description."),
    ] = False
    preview: Annotated[
        str,
        Field(
            description="Optional: a mockup or code to compare, shown as monospace text. Only "
            "when the choices differ in something to see."
        ),
    ] = ""
    reason: Annotated[str, Field(description="Deprecated: put why in description.")] = ""


def register_tools(mcp: FastMCP, services: Services) -> None:
    """Add the question tools to `mcp`."""
    talk = services.get(TalkService)
    repository_of = services.get(TicketRepositories)

    @mcp.tool(annotations=APPENDS)
    async def ask_question(
        question: Annotated[
            str,
            Field(
                description=f"One focused question, at most {QUESTION_LIMIT} characters.",
                min_length=1,
                max_length=QUESTION_LIMIT,
            ),
        ],
        choices: Annotated[
            list[ChoiceOffered] | None,
            Field(
                description=(
                    f"None for a question answered in words, else {CHOICES_MIN} to {CHOICES_MAX} "
                    "distinct choices; the owner can always type another answer, so add no "
                    "'Other'."
                ),
                max_length=CHOICES_MAX,
            ),
        ] = None,
        several: Annotated[
            bool, Field(description="Whether more than one choice may be picked.")
        ] = False,
        topic: Annotated[
            str,
            Field(
                description=f"A label of at most {TOPIC_LIMIT} characters naming what it is "
                "about, for example Auth method or Library.",
                max_length=TOPIC_LIMIT,
            ),
        ] = "",
        document: Annotated[str | None, Field(description="The document it is about.")] = None,
        ticket_id: TicketId = None,
    ) -> QuestionAsked:
        """Ask the owner one focused question that blocks you, with choices and a recommended one; then end your turn: the answer is recorded on the ticket for the next run to read. Asking an equal open question again returns the first. Use only when a decision or permission genuinely blocks progress."""  # noqa: E501
        actor = current_actor()
        ticket = await scope_ticket(actor, ticket_id, repository_of)
        offered = [Choice(**choice.model_dump()) for choice in choices or []]
        return await talk.ask(
            ticket,
            question,
            offered,
            document=document,
            several=several,
            topic=topic,
            by=actor.subject,
            run_id=actor.run_id,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def list_questions(
        ticket_id: Annotated[
            str | None, Field(description="A run: its own. The owner: leave out for every ticket.")
        ] = None,
        status: StatusFilter = "open",
        document: str | None = None,
        limit: PageLimit = 25,
        cursor: Annotated[str | None, Field(description="next_cursor of the last page.")] = None,
    ) -> QuestionPage:
        """List questions with their choices and answers, by status (open by default), for one ticket or, for the owner, all. Use to see what waits on the owner or what was decided; answer_question takes a question's id."""  # noqa: E501
        actor = current_actor()
        ticket = (
            None
            if actor.role is Role.OWNER and ticket_id is None
            else await scope_ticket(actor, ticket_id, repository_of)
        )
        where = QuestionFilter(ticket_id=ticket, status=status, document=document)
        return await talk.list(where, limit=limit, cursor=cursor)

    @mcp.tool(annotations=REPLACES)
    async def answer_question(
        question_id: Annotated[int, Field(description="The id list_questions gives.", ge=1)],
        answer: Annotated[str, Field(description="Words, when no choice is picked.")] = "",
        choices: Annotated[list[str] | None, Field(description="Choice texts picked.")] = None,
        replace: Annotated[bool, Field(description="Replace an answer already given.")] = False,
    ) -> Answered:
        """Answer a question by its id with the choices picked or with words; picks win over words. An answered question is refused unless replace is true. Use when the owner has decided what a question asks."""  # noqa: E501
        actor = current_actor()
        reply = Reply(choices=choices or [], text=answer)
        return await talk.answer(
            question_id, reply, replace=replace, by=actor.subject, channel="mcp"
        )
