"""Read the owner's private QA cases from board state."""

import os
import stat
from pathlib import Path

import anyio

from code_factory.platform.errors import UnavailableError
from code_factory.tickets.rules import ticket_id, ticket_number

MAX_CASE_BYTES = 32_768


def _read(directory: Path, name: str) -> str | None:
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(name, flags, dir_fd=parent), "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                msg = "the QA cases are not a regular file"
                raise ValueError(msg)
            text = file.read(MAX_CASE_BYTES + 1)
    finally:
        os.close(parent)
    if len(text) > MAX_CASE_BYTES:
        msg = "the QA cases file exceeds 32 KiB"
        raise ValueError(msg)
    return text.decode("utf-8").strip() or None


class QaHoldouts:
    """The cases of one ticket, stored outside its repository and documents."""

    def __init__(self, state: Path) -> None:
        self._directory = state / "qa-holdouts"

    async def cases(self, ticket: str) -> str | None:
        """Return private cases for this ticket if the owner supplied them."""
        name = f"{ticket_id(ticket_number(ticket))}.md"
        try:
            return await anyio.to_thread.run_sync(_read, self._directory, name)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            msg = "the private QA cases could not be read; check the board's qa-holdouts directory"
            raise UnavailableError(msg) from error
