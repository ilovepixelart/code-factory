"""What the talk service shares: errors, answers and the conversions of rows."""

from datetime import UTC, datetime
from typing import Any

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.talk.models import (
    Answer,
    Choice,
    Message,
    Question,
    QuestionFilter,
    QuestionStatus,
)
from code_factory.talk.repository import OPEN
from code_factory.talk.rules import (
    MAX_ID,
    document_name,
    ticket_id,
    ticket_number,
)
from code_factory.talk.tables import AnswerRow, PostRow, QuestionRow

OPEN_LIMIT = 20
PAGE_DEFAULT = 25
PAGE_MAX = 100


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


def no_ticket(number: int) -> NotFoundError:
    """The sentence for a ticket that does not exist."""
    return NotFoundError(f"{ticket_id(number)} does not exist; list the tickets to find its id")


def check_id(question_id: int) -> int:
    """`question_id` when the database can hold it; else the same error as for an unknown one."""
    if not 0 < question_id < MAX_ID:
        raise no_question(question_id)
    return question_id


def no_question(question_id: int) -> NotFoundError:
    """The sentence for a question that does not exist."""
    return NotFoundError(f"no question {question_id}")


def status(row: QuestionRow, answer: AnswerRow | None) -> QuestionStatus:
    """Withdrawn once it was; else answered once it has an answer; else open.

    The answer read decides too: it may have landed after the question row was read.
    """
    if row.withdrawn_at is not None:
        return "withdrawn"
    return "answered" if row.answered_at is not None or answer is not None else "open"


def to_answer(row: AnswerRow) -> Answer:
    """An answer row as its answer."""
    return Answer(
        id=row.id,
        text=row.text,
        picked=list(row.picked),
        by=row.by,
        channel=row.channel,  # ty: ignore[invalid-argument-type]  # the check constraint holds it
        created_at=row.created_at,
    )


def to_question(row: QuestionRow, index: int, answer: AnswerRow | None) -> Question:
    """A question row with its position and newest answer as its answer."""
    picked = set(answer.picked) if answer else set()
    return Question(
        id=row.id,
        ticket_id=ticket_id(row.ticket_number),
        document=row.document,
        index=index,
        text=row.text,
        topic=row.topic,
        several=row.several,
        choices=[
            Choice(
                text=c["text"],
                recommended=c["recommended"],
                reason=c["reason"],
                description=c.get("description", ""),
                preview=c.get("preview", ""),
                ticked=c["text"] in picked,
            )
            for c in row.choices
        ],
        asked_by=row.asked_by,
        run_id=row.run_id,
        created_at=row.created_at,
        status=status(row, answer),
        answer=to_answer(answer) if answer else None,
    )


def to_message(row: PostRow) -> Message:
    """A message row as its answer."""
    return Message(
        id=row.id,
        ticket_id=ticket_id(row.ticket_number),
        author=row.author,
        text=row.text,
        route=row.route,  # ty: ignore[invalid-argument-type]  # the check constraint holds it
        created_at=row.created_at,
        delivered_at=row.delivered_at,
        delivered_to=row.delivered_to,
    )


def question_conditions(where: QuestionFilter) -> list[Any]:
    """The where-clauses a question filter selects by."""
    conditions: list[Any] = []
    if where.ticket_id is not None:
        conditions.append(QuestionRow.ticket_number == ticket_number(where.ticket_id))
    if where.status == "open":
        conditions.extend(OPEN)
    elif where.status == "answered":
        conditions.extend(
            (QuestionRow.answered_at.is_not(None), QuestionRow.withdrawn_at.is_(None))
        )
    if where.document is not None:
        conditions.append(QuestionRow.document == document_name(where.document))
    return conditions


def bad_cursor() -> BadRequestError:
    """The sentence for a cursor no page of this list gave."""
    return BadRequestError("that cursor is not one this list gave; start again without it")


def page_after(text: str | None) -> int | None:
    """The id a page continues after; `None` for no cursor, an error for one that is no id."""
    if text is None or text == "":
        return None
    if not (text.isascii() and text.isdigit()) or int(text) >= MAX_ID:
        raise bad_cursor()
    return int(text)
