"""Tokens as the rest of the program sees them: DTOs, never the digest or the token value again."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, SecretStr

from code_factory.platform.identity import Role


class TokenKind(StrEnum):
    """What a token is for."""

    RUN = "run"  # a board run's access to MCP, bound to a run and its ticket
    OWNER = "owner"  # the owner's long-lived MCP credential
    NONCE = "nonce"  # a one-time sign-in link value, exchanged for a session
    SESSION = "session"  # the owner's browser session, the value of the owner cookie


# What `AuthService.verify_token` accepts unless the caller names other kinds: the credentials of
# an MCP client. A session or nonce is never a bearer for MCP.
BEARER_KINDS = frozenset({TokenKind.RUN, TokenKind.OWNER})


class IssuedToken(BaseModel):
    """A token at the moment it is issued: the only time its value exists outside its holder."""

    model_config = ConfigDict(frozen=True)

    id: int
    token: SecretStr
    expires_at: datetime


class TokenInfo(BaseModel):
    """A stored token without its value."""

    model_config = ConfigDict(frozen=True)

    id: int
    kind: TokenKind
    subject: str
    label: str
    run_id: str | None
    ticket_id: str | None
    stage: str | None
    repository: str | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class Description(BaseModel):
    """What a caller is, for `whoami`."""

    model_config = ConfigDict(frozen=True)

    role: Role
    subject: str
    run_id: str | None
    ticket_id: str | None
    stage: str | None
    repository: str | None
    expires_at: datetime
