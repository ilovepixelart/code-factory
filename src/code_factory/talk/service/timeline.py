"""A ticket's talk as timeline entries, and the cursor that pages them."""

import builtins
from datetime import datetime
from typing import Any

from code_factory.talk.models import (
    EntryKind,
    TalkEntry,
)
from code_factory.talk.repository import ENTRY_RANK
from code_factory.talk.service.common import MAX_ID, bad_cursor
from code_factory.talk.tables import AnswerRow, PostRow, QuestionRow


def entry_cursor(text: str | None) -> tuple[datetime, int, int] | None:
    """The place `(at, kind rank, id)` a timeline page continues after."""
    if text is None or text == "":
        return None
    try:
        when, rank, last = text.split("|")
        at = datetime.fromisoformat(when)
        found = (at, int(rank), int(last))
    except ValueError:
        raise bad_cursor() from None
    if at.tzinfo is None or not (0 <= found[1] < len(ENTRY_RANK)) or not (0 <= found[2] < MAX_ID):
        raise bad_cursor()
    return found


def entry_cursor_text(key: tuple[datetime, int, int] | None) -> str | None:
    """The cursor text of the entry after which the next page begins."""
    return None if key is None else f"{key[0].isoformat()}|{key[1]}|{key[2]}"


def timeline(
    ticket: str, kind: EntryKind, fields: tuple[int, datetime, str, str], data: dict[str, Any]
) -> tuple[tuple[datetime, int, int], TalkEntry]:
    """A row of the talk as a timeline entry, with its place in the order."""
    entry_id, at, by, text = fields
    entry = TalkEntry(kind=kind, id=entry_id, ticket_id=ticket, at=at, by=by, text=text, data=data)
    return (at, ENTRY_RANK[kind], entry_id), entry


def _question_entry(ticket: str, row: QuestionRow) -> tuple[tuple[datetime, int, int], TalkEntry]:
    data = {"document": row.document, "choices": row.choices, "several": row.several}
    return timeline(ticket, "question", (row.id, row.created_at, row.asked_by, row.text), data)


def _answer_entry(
    ticket: str, answer: AnswerRow, words: str
) -> tuple[tuple[datetime, int, int], TalkEntry]:
    data = {
        "question_id": answer.question_id,
        "question": words,
        "picked": list(answer.picked),
        "channel": answer.channel,
    }
    fields = (answer.id, answer.created_at, answer.by, answer.text)
    return timeline(ticket, "answer", fields, data)


def _post_entry(
    ticket: str, kind: EntryKind, row: PostRow
) -> tuple[tuple[datetime, int, int], TalkEntry]:
    data: dict[str, Any] = (
        {"path": row.path, "line": row.line}
        if kind == "comment"
        else {"route": row.route, "delivered": row.delivered_at is not None}
    )
    return timeline(ticket, kind, (row.id, row.created_at, row.author, row.text), data)


def entries_of(
    ticket: str, kind: EntryKind, rows: builtins.list[Any]
) -> builtins.list[tuple[tuple[datetime, int, int], TalkEntry]]:
    """Timeline entries, each with its place in the order, for the rows of one kind."""
    if kind == "question":
        return [_question_entry(ticket, row) for row in rows]
    if kind == "answer":
        return [_answer_entry(ticket, answer, words) for answer, words in rows]
    return [_post_entry(ticket, kind, row) for row in rows]
