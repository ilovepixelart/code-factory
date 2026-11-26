"""The message for each Inbox item, the target's address rule and what a reply may say.

A message names its kind, ticket and place on the Inbox and nothing an item holds besides: it
leaves the machine.
"""

import hashlib
import json
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

from code_factory.push.models import FORMATS, Item, Message

# The Inbox sections whose items need a reply, in the order they are sent.
REPLIES = (
    "main",
    "questions",
    "permissions",
    "screens",
    "sessions",
    "stopped",
    "failing",
    "mergeable",
    "idle",
)
# How long a link answers: a permission's hook gives up after 540 s; a question waits a day.
PERMISSION_WAIT_S = 540.0
QUESTION_WAIT_S = 86_400.0
REFUSAL = "this link was used, has expired or is not known"
PLAIN_HTTP = "plain http goes only to localhost or 127.0.0.1; use https://"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_KINDS = {
    "main": ("main", ": the default branch fails its checks"),
    "questions": ("question", ": a question waits for your answer"),
    "permissions": ("permission", ": an agent asks permission"),
    "sessions": ("session", "A session waits for permission"),
    "stopped": ("stopped", ": an agent stopped"),
    "screens": ("screens", ": screens wait for your approval"),
    "mergeable": ("merge", " is ready to merge"),
    "failing": ("failing", ": CI failed on its pull request"),
    "idle": ("idle", " has an idle pull request"),
}
_IDENTITY: dict[str, tuple[tuple[str, ...], ...]] = {
    "questions": (("question", "document"), ("question", "index"), ("question", "text")),
    "permissions": (("request", "id"),),
    "sessions": (("session", "session_id"), ("since",)),
    "stopped": (("since",),),
    "screens": (("reason",),),
    "mergeable": (("reason",),),
    "failing": (("reason",),),
    "idle": (("reason",), ("since",)),
    # One message while a default branch fails: later runs keep the pass they follow.
    "main": (("main", "repository"), ("main", "passed")),
}
_TICKET = (("ticket", "repository"), ("ticket", "id"))


def _text_at(item: Item, path: Sequence[str]) -> str:
    found: Any = item
    for key in path:
        found = found.get(key) if isinstance(found, dict) else None
    if found is None:
        return ""
    if isinstance(found, str):
        return found
    return json.dumps(found)


def address_refusal(format_: str, url: str) -> str | None:
    """Why a target is not taken: unknown format, a URL that is not plain, or plain http away.

    Plain http goes only to this machine, since a message names the owner's tickets.
    """
    if format_ not in FORMATS:
        return f"a push format is {' or '.join(FORMATS)}"
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or parts.hostname in {None, ""}:
        return "a push address is an http or https URL"
    if parts.username is not None or parts.password is not None or parts.fragment != "":
        return "a push address carries no user, password or fragment"
    if parts.scheme == "http" and parts.hostname not in LOCAL_HOSTS:
        return PLAIN_HTTP
    return None


def identity(section: str, item: Item) -> tuple[str, ...] | None:
    """What names an item while it waits; None for a section that needs no reply."""
    fields = _IDENTITY.get(section)
    if fields is None:
        return None
    return tuple(_text_at(item, path) for path in (*_TICKET, *fields))


def anchor(section: str, item: Item) -> str:
    """Where the item waits on the Inbox page, made as the page makes its rows' ids."""
    repository, ticket = _text_at(item, ("ticket", "repository")), _text_at(item, ("ticket", "id"))
    if section == "questions":
        document = _text_at(item, ("question", "document"))
        return f"question-{repository}-{ticket}-{document}-{_text_at(item, ('question', 'index'))}"
    if section == "permissions":
        return f"perm-{_text_at(item, ('request', 'id'))}"
    if section == "sessions":
        return f"sessions-{_text_at(item, ('session', 'session_id'))}"
    if section == "main":
        return f"main-{_text_at(item, ('main', 'repository'))}"
    return f"{section}-{repository}-{ticket}"


def _sentence(section: str, item: Item, ticket: str | None, repository: str | None) -> str:
    _, words = _KINDS[section]
    named = ticket is not None and ticket != ""
    if named and section == "failing" and item.get("kind") == "stuck":
        return f"{ticket}: {_text_at(item, ('note',))}"
    if named and section != "sessions":
        return f"{ticket}{words}"
    if section == "main" and repository is not None and repository != "":
        return f"{repository}{words}"
    return words


def message(section: str, item: Item) -> Message | None:
    """The message for an item of the Inbox's `section`; None for a section that needs no reply."""
    parts = identity(section, item)
    if parts is None or section not in _KINDS:
        return None
    ticket = (item.get("ticket") or {}).get("id")
    repository = (item.get("ticket") or {}).get("repository") or (item.get("main") or {}).get(
        "repository"
    )
    digest = hashlib.sha256("\0".join((section, *parts)).encode()).hexdigest()[:16]
    return Message(
        digest=digest,
        kind=_KINDS[section][0],
        repository=repository,
        ticket=ticket,
        text=_sentence(section, item, ticket, repository),
        anchor=anchor(section, item),
        request=(item.get("request") or {}).get("id") if section == "permissions" else None,
        question=parts if section == "questions" else None,
    )


def messages(page: dict[str, Any]) -> list[Message]:
    """Every item of an Inbox answer needing a reply, in `REPLIES` order, each section's own."""
    found = (message(section, item) for section in REPLIES for item in page.get(section, []))
    return [m for m in found if m is not None]


def webhook_body(message: Message, link: str, reply: str) -> str:
    """The kind, repository and ticket (null for a session), sentence, link and any reply link."""
    body: dict[str, Any] = {
        "kind": message.kind,
        "repository": message.repository,
        "ticket": message.ticket,
        "text": message.text,
        "link": link,
    }
    if reply:
        body["reply"] = reply
    return json.dumps(body)


def ntfy_headers(link: str, reply: str) -> dict[str, str]:
    """Ntfy's title, its click target and, with a reply link, the action that opens it."""
    headers = {"Content-Type": "text/plain; charset=utf-8", "Title": "code-factory", "Click": link}
    if reply:
        headers["Actions"] = f"view, Reply, {reply}"
    return headers


def bad_reply(question: Item, choices: Sequence[str], answer: str) -> str | None:
    """Why `choices` or `answer` cannot answer `question`: checked before the link is spent."""
    offered = {c.get("text") for c in question.get("choices", [])}
    if not choices and not answer.strip():
        return "pick a choice or write an answer"
    if any(choice not in offered for choice in choices):
        return "that is not one of the question's choices"
    if len(choices) > 1 and question.get("several") is not True:
        return "pick one choice"
    return None


def still_answers(kept_request: str, minted_at: float, now: float) -> bool:
    """Whether a token minted at `minted_at` answers now: a request's or a question's wait."""
    wait = PERMISSION_WAIT_S if kept_request else QUESTION_WAIT_S
    return now - minted_at < wait
