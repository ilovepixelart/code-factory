"""Run tokens: their form, their digest, where a request carries one and when one is dead."""

import hashlib
import re
import secrets
from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

PREFIX = "cfb_"
_WELL_FORMED = re.compile(r"cfb_[A-Za-z0-9_-]{43}")
_BEARER = "bearer "


class Lifetime(Protocol):
    """What decides whether a token is alive."""

    @property
    def ended_at(self) -> datetime | None:
        """When the run ended, if it did."""
        ...

    @property
    def expires_at(self) -> datetime:
        """The hard backstop."""
        ...


def new_token() -> str:
    """A token: the prefix and 256 random bits in URL-safe base64."""
    return PREFIX + secrets.token_urlsafe(32)


def digest(token: str) -> str:
    """The lowercase hex SHA-256 of the token, the only form that is stored."""
    return hashlib.sha256(token.encode()).hexdigest()


def well_formed(token: str) -> bool:
    """Whether the text has the exact shape of a token: the only gate before any lookup."""
    return _WELL_FORMED.fullmatch(token) is not None and token.isascii()


def _first(headers: Sequence[tuple[str, str]], name: str) -> str | None:
    return next((value for key, value in headers if key.lower() == name), None)


def token_of(headers: Sequence[tuple[str, str]]) -> str | None:
    """The token a request carries: `Authorization: Bearer`, else `x-api-key`.

    Only the first value of a repeated header counts and nothing is trimmed, so a padded value is
    malformed rather than repaired.
    """
    auth = _first(headers, "authorization")
    if (
        auth is not None
        and auth[: len(_BEARER)].lower() == _BEARER
        and auth[len(_BEARER) : len(_BEARER) + 1] != " "
    ):
        return auth[len(_BEARER) :]
    return _first(headers, "x-api-key")


def token_state(row: Lifetime, now: datetime) -> Literal["live", "ended", "expired"]:
    """Whether the token lives; an ended and an expired one are refused alike."""
    if row.ended_at is not None:
        return "ended"
    return "expired" if row.expires_at <= now else "live"
