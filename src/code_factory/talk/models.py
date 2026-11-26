"""What the talk module hands out and takes in: plain data, no behaviour."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

QuestionStatus = Literal["open", "answered", "withdrawn"]
StatusFilter = Literal["open", "answered", "all"]
Channel = Literal["http", "reply", "mcp", "acp", "cli"]
Route = Literal["run", "next_run"]
EntryKind = Literal["question", "answer", "comment", "message"]


class QuestionWait(BaseModel):
    """First-answer wait over the questions answered in a given window."""

    answered: int
    median_seconds: float | None


class Choice(BaseModel):
    """One choice a question offers; `ticked` is set on the picked ones of an answered question."""

    text: str
    recommended: bool = False
    reason: str = ""
    """Why it is recommended; written by questions asked before `description` existed."""
    description: str = ""
    """What picking it means, in a sentence or two."""
    preview: str = ""
    """A mockup or code to compare, shown as monospace text."""
    ticked: bool = False


class Reply(BaseModel):
    """What the owner answers: choices the question offers, or free text. Picks win over text."""

    choices: list[str] = Field(default_factory=list)
    text: str = ""


class Answer(BaseModel):
    """One answer to a question; the current one is the newest."""

    id: int
    text: str
    picked: list[str]
    by: str
    channel: Channel
    created_at: datetime


class Question(BaseModel):
    """A question an agent asked the owner.

    `index` is its position among the ticket's questions of the same document, which is how the
    app addresses it.
    """

    id: int
    ticket_id: str
    document: str
    index: int
    text: str
    topic: str = ""
    """A label of at most 12 characters naming what it is about, for scanning a list."""
    several: bool
    choices: list[Choice]
    asked_by: str
    run_id: str
    created_at: datetime
    status: QuestionStatus
    answer: Answer | None = None

    def shown(self) -> dict[str, Any]:
        """The question as the Inbox shows it: its document named with `.md`, its choices."""
        return {
            "document": f"{self.document}.md" if self.document else "",
            "index": self.index,
            "text": self.text,
            "topic": self.topic,
            "choices": [choice.model_dump() for choice in self.choices],
            "several": self.several,
        }

    def on_ticket(self) -> dict[str, Any]:
        """The question as a ticket shows it: as shown, with its answer and the picks ticked."""
        picked = set(self.answer.picked) if self.answer else set()
        shown = self.shown()
        return {
            **shown,
            "answer": self.answer.text if self.answer else "",
            "answered_by": self.answer.channel if self.answer else "",
            "choices": [{**c, "ticked": c["text"] in picked} for c in shown["choices"]],
        }


class QuestionFilter(BaseModel):
    """Which questions to list: of one ticket (or all), by status, of one document."""

    ticket_id: str | None = None
    status: StatusFilter = "open"
    document: str | None = None


class QuestionPage(BaseModel):
    """A page of questions by id; `next_cursor` continues it, `None` at its end."""

    items: list[Question]
    next_cursor: str | None


class QuestionAsked(BaseModel):
    """The answer to `ask`: `created` is false when the same open question was there already."""

    question_id: int
    created: bool
    status: QuestionStatus


class Answered(BaseModel):
    """The answer to answering: `text` is the question's, `answer` the words recorded."""

    question_id: int
    ticket_id: str
    text: str
    answer: str
    status: QuestionStatus


class PostId(BaseModel):
    """The id of a stored comment."""

    id: int


class Message(BaseModel):
    """The owner's message on a ticket, for the running agent or the next run."""

    id: int
    ticket_id: str
    author: str
    text: str
    route: Route
    created_at: datetime
    delivered_at: datetime | None = None
    delivered_to: str = ""


class NewsEntry(BaseModel):
    """One thing said on a ticket, as a fact for `news_lines`; `question` names an answer's."""

    kind: Literal["answer", "message", "comment"]
    text: str
    author: str = ""
    question: str = ""
    message_id: int | None = None


class News(BaseModel):
    """What a session has not been given: the text, how far it reads, the whole messages in it."""

    text: str
    through_post: int
    through_answer: int
    message_ids: list[int]


class TalkEntry(BaseModel):
    """One record of the talk on a ticket for its timeline."""

    kind: EntryKind
    id: int
    ticket_id: str
    at: datetime
    by: str
    text: str
    data: dict[str, Any]


class TalkEntryPage(BaseModel):
    """A page of timeline entries, oldest first; `next_cursor` continues it."""

    items: list[TalkEntry]
    next_cursor: str | None
