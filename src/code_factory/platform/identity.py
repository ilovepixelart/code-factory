"""Who is calling: the identity every transport resolves a credential to.

The auth module implements `ActorVerifier`; `platform.mcp` and `platform.web` depend on this
description only, so they know no module.
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict

# The shape of every token the auth module mints: three letters `cf?` and an underscore, then 43
# url-safe characters (256 bits). Logging redacts anything that matches.
TOKEN_PATTERN = re.compile(r"cf[a-z]_[A-Za-z0-9_-]{43}")


def redact(text: str) -> str:
    """`text` with every token replaced by `cf?_[redacted]`."""
    return TOKEN_PATTERN.sub(lambda found: f"{found.group()[:4]}[redacted]", text)


class Role(StrEnum):
    """What a caller may do: one ticket in one stage, the board, or everything."""

    RUN = "run"
    COORDINATOR = "coordinator"
    OWNER = "owner"


class Actor(BaseModel):
    """The verified caller of one request."""

    model_config = ConfigDict(frozen=True)

    role: Role
    subject: str  # `run:<id>` or `owner:<label>`; the author recorded on every write
    token_id: int
    run_id: str | None = None
    ticket_id: str | None = None
    stage: str | None = None
    repository: str | None = None
    expires_at: datetime


class ActorVerifier(Protocol):
    """Resolves a bearer token to its actor, or `None` when it is unknown, ended or revoked."""

    async def verify_token(self, token: str) -> Actor | None:
        """The actor for `token`, or `None`."""
        ...
