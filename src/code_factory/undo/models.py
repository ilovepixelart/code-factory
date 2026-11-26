"""What the undo service answers and takes."""

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

# A kind's inverse: given the stored payload and who asks, put the change back or raise the
# platform error that says why it cannot be.
UndoHandler = Callable[[dict[str, Any], str], Awaitable[None]]


class Changed(BaseModel):
    """The app's answer to a write: a notice for the toast and the token that takes it back.

    `undo` is `None` when the change cannot be taken back; the app shows no Undo button then.
    """

    notice: str
    undo: str | None
