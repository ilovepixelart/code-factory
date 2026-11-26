"""The talk rules: pure functions over the models, with the sentences the owner reads."""

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.talk.models import Choice, NewsEntry, Question, Route

PREFIX = "CF-"
MAX_ID = 2**63
QUESTION_LIMIT = 1000
CHOICE_LIMIT = 200
# A question offers no choice (answered in words) or two to four, the recommended one first.
CHOICES_MIN = 2
CHOICES_MAX = 4
TOPIC_LIMIT = 12
DESCRIPTION_LIMIT = 500
PREVIEW_LIMIT = 4000
NEWS_LIMIT = 10_000
# The runtimes that take an owner's message while a run works: claude after its next tool result,
# codex as a steer.
INTERACTIVE = frozenset({"claude", "codex"})
SENT_TO_RUN = "Sent to the running agent"
KEPT_FOR_NEXT_RUN = "Kept for the next run"
_LINE_BREAKS = frozenset("\n\r\x0b\x0c\x1c\x1d\x1e\x85") | {chr(0x2028), chr(0x2029)}


def _in_range(digits: str) -> bool:
    """Whether the digits are an id from 1 to the database's largest; long ones are not parsed."""
    return len(digits) <= len(str(MAX_ID)) and 0 < int(digits) < MAX_ID


def ticket_number(text: str) -> int:
    """The number of an id `CF-<n>`; `BadRequestError` for anything else."""
    digits = text.removeprefix(PREFIX)
    if digits == text or not (digits.isascii() and digits.isdigit()) or not _in_range(digits):
        msg = f"{text!r} is not a ticket id CF-<n>: write CF and a number from 1, as in CF-12"
        raise BadRequestError(msg)
    return int(digits)


def ticket_id(number: int) -> str:
    """The id a person reads, `CF-<n>`."""
    return f"{PREFIX}{number}"


def one_line(text: str) -> str:
    """The words of `text` joined by single spaces."""
    return " ".join(text.split())


def has_line_break(text: str) -> bool:
    """Whether `text` holds a character that ends a line."""
    return any(char in _LINE_BREAKS for char in text)


def document_name(document: str | None) -> str:
    """A ticket document as stored: `spec` for `spec`, `spec.md` or nothing (`''`)."""
    return (document or "").strip().removesuffix(".md")


def _check_choice(choice: Choice) -> Choice:
    text = choice.text.strip()
    if not text:
        raise BadRequestError("a choice needs words")
    if has_line_break(text):
        raise BadRequestError("a choice holds a line break")
    if len(text) > CHOICE_LIMIT:
        raise BadRequestError(f"a choice is at most {CHOICE_LIMIT} characters")
    description = choice.description.strip()
    if len(description) > DESCRIPTION_LIMIT:
        raise BadRequestError(f"a choice's description is at most {DESCRIPTION_LIMIT} characters")
    if len(choice.preview) > PREVIEW_LIMIT:
        raise BadRequestError(f"a choice's preview is at most {PREVIEW_LIMIT} characters")
    return Choice(
        text=text,
        recommended=choice.recommended,
        reason=choice.reason.strip(),
        description=description,
        preview=choice.preview.rstrip(),
    )


def check_topic(topic: str) -> str:
    """The topic stripped, or `BadRequestError` when it is too long or holds a line break."""
    words = topic.strip()
    if has_line_break(words):
        raise BadRequestError("a topic holds a line break")
    if len(words) > TOPIC_LIMIT:
        raise BadRequestError(f"a topic is at most {TOPIC_LIMIT} characters, as a label: {words}")
    return words


def check_question(text: str, choices: list[Choice], *, several: bool) -> tuple[str, list[Choice]]:
    """The question's text and choices normalised, or `BadRequestError`."""
    words = text.strip()
    if not words:
        raise BadRequestError("a question needs words")
    if len(words) > QUESTION_LIMIT:
        raise BadRequestError(f"a question is at most {QUESTION_LIMIT} characters")
    if len(choices) > CHOICES_MAX:
        raise BadRequestError(f"a question offers at most {CHOICES_MAX} choices")
    if 0 < len(choices) < CHOICES_MIN:
        raise BadRequestError(
            f"a question offers no choice or {CHOICES_MIN} to {CHOICES_MAX}; "
            "one choice is a statement, so ask it in words"
        )
    checked = [_check_choice(choice) for choice in choices]
    checked.sort(key=lambda choice: not choice.recommended)
    seen: set[str] = set()
    for choice in checked:
        if choice.text in seen:
            raise BadRequestError(f"a choice is offered twice: {choice.text}")
        seen.add(choice.text)
    if not several and sum(choice.recommended for choice in checked) > 1:
        raise BadRequestError("only one choice is recommended here")
    return words, checked


def _chosen(question: Question, picked: list[str]) -> list[str]:
    """The picked choices in the question's order; refuses a stray or a second pick."""
    if any(has_line_break(pick) for pick in picked):
        raise BadRequestError("a choice holds a line break")
    offered = [choice.text for choice in question.choices]
    wanted = {pick.strip() for pick in picked}
    stray = next((pick.strip() for pick in picked if pick.strip() not in offered), None)
    if stray is not None:
        listed = ", ".join(offered) if offered else "it offers none"
        raise BadRequestError(f"{stray} is not one of its choices: {listed}")
    chosen = [text for text in offered if text in wanted]
    if len(chosen) > 1 and not question.several:
        raise BadRequestError("one choice is picked here")
    return chosen


def check_reply(question: Question, picked: list[str], text: str) -> tuple[str, list[str]]:
    """The words an answer records and the choices it picked, or `BadRequestError`."""
    if picked:
        chosen = _chosen(question, picked)
        return one_line(", ".join(chosen)), chosen
    if question.choices and has_line_break(text.strip()):
        raise BadRequestError("the answer holds a line break")
    words = one_line(text)
    if not words:
        raise BadRequestError("an answer and a question are needed")
    return words, []


def reply_gap(question: Question, picked: list[str], text: str) -> str | None:
    """Why a reply link's answer cannot be taken, checked before the link is spent.

    It names the three link sentences and otherwise says what `check_reply` would refuse, so a
    reply it passes is one `check_reply` takes.
    """
    if not picked and not text.strip():
        return "pick a choice or write an answer"
    offered = {choice.text for choice in question.choices}
    if any(pick.strip() not in offered for pick in picked):
        return "that is not one of the question's choices"
    if len({pick.strip() for pick in picked}) > 1 and not question.several:
        return "pick one choice"
    try:
        check_reply(question, picked, text)
    except BadRequestError as refusal:
        return str(refusal)
    return None


def answer_target(questions: list[Question], document: str, index: int, shown: str) -> Question:
    """The question at (`document`, `index`), when it still reads `shown`."""
    if not shown.strip():
        raise BadRequestError("the text of the question answered is needed")
    name = document_name(document)
    found = next((q for q in questions if q.document == name and q.index == index), None)
    if found is None:
        raise NotFoundError(f"no question {index} in {document}")
    if found.text.strip() != shown.strip():
        raise ConflictError(f"the question changed: it now asks {found.text.strip()}")
    return found


def comment_text(text: str, path: str | None, line: int | None) -> str:
    """A comment's words, led by `path:line:` when it is about a place."""
    words = text.strip()
    if not words:
        raise BadRequestError("an empty comment says nothing")
    place = (path or "").strip()
    if not place:
        return words
    return f"{place}:{line}: {words}" if line is not None else f"{place}: {words}"


def message_text(text: str) -> str:
    """A message's words, or `BadRequestError` when there are none."""
    words = text.strip()
    if not words:
        raise BadRequestError("an empty message says nothing")
    return words


def route_message(runtime: str, *, running: bool) -> Route:
    """`run` when a run is active and its runtime takes input while it works, else `next_run`."""
    return "run" if running and runtime in INTERACTIVE else "next_run"


def route_notice(route: Route) -> str:
    """What the owner is told of where a message went."""
    return SENT_TO_RUN if route == "run" else KEPT_FOR_NEXT_RUN


def _fact(entry: NewsEntry, ticket: str) -> str:
    if entry.kind == "answer":
        return f'The owner answered "{entry.question}" on {ticket}: {entry.text}'
    if entry.kind == "message":
        return (
            f"A message from the owner on {ticket}, sent while you work. "
            f"Take it as the owner's instruction: {entry.text}"
        )
    return f"{entry.author} commented on {ticket}: {entry.text}"


def _whole(entries: list[NewsEntry], ticket: str, limit: int) -> int:
    """How many leading entries fit whole in `limit` characters."""
    used = 0
    for count, entry in enumerate(entries):
        used += len(_fact(entry, ticket)) + (1 if used else 0)
        if used > limit:
            return count
    return len(entries)


def fitting(entries: list[NewsEntry], ticket: str, limit: int = NEWS_LIMIT) -> int:
    """How many leading entries a session has been given once the text is cut at `limit`.

    The first is always given, cut if it alone is too long, so that one entry cannot stall a
    session for good.
    """
    return max(_whole(entries, ticket, limit), 1) if entries else 0


def news_lines(
    entries: list[NewsEntry], ticket: str, limit: int = NEWS_LIMIT
) -> tuple[str, list[int]]:
    """One fact per line for the entries that fit, and the ids of the messages kept whole.

    An entry that does not fit is left out and stays unread; only the first, when it alone is too
    long, is given cut at `limit` characters (and its message, cut, is not whole).
    """
    given = entries[: fitting(entries, ticket, limit)]
    text = "\n".join(_fact(entry, ticket) for entry in given)[:limit]
    kept = entries[: _whole(entries, ticket, limit)]
    return text, [entry.message_id for entry in kept if entry.message_id is not None]
