"""What the push module keeps and sends."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Format = Literal["ntfy", "webhook"]
FORMATS: tuple[Format, ...] = ("ntfy", "webhook")


class Target(BaseModel):
    """Where messages go: `ntfy` posts the sentence, `webhook` posts JSON."""

    model_config = ConfigDict(frozen=True)

    format: Format
    url: str


@dataclass(frozen=True)
class Message:
    """One message: the item's digest, its kind, where it waits and the sentence saying so.

    `anchor` is the link's part after `/inbox#`. `request` is the permission request it announces
    and `question` the question's identity, which a reply link can answer.
    """

    digest: str
    kind: str
    repository: str | None
    ticket: str | None
    text: str
    anchor: str
    request: str | None = None
    question: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Kept:
    """A reply token as the board keeps it: by digest, for a request or a question's identity."""

    request: str
    question: tuple[str, ...]
    minted_at: float


Item = dict[str, Any]
