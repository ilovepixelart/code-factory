"""Token format, digest and lifetime: pure, so the expected values can be worked by hand."""

import base64
import hashlib
from datetime import datetime, timedelta

from code_factory.auth.models import TokenKind
from code_factory.platform.errors import BadRequestError

ENTROPY_BYTES = 32  # 256 bits
ENCODED_LENGTH = 43  # unpadded url-safe base64 of 32 bytes
MAX_LABEL = 64

PREFIX: dict[TokenKind, str] = {
    TokenKind.RUN: "cfr_",
    TokenKind.OWNER: "cfo_",
    TokenKind.NONCE: "cfn_",
    TokenKind.SESSION: "cfs_",
}

LONGEST_LIFETIME: dict[TokenKind, timedelta] = {
    TokenKind.RUN: timedelta(days=7),
    TokenKind.OWNER: timedelta(days=366),
    TokenKind.NONCE: timedelta(minutes=5),
    TokenKind.SESSION: timedelta(days=366),
}

_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
_BY_PREFIX = {prefix: kind for kind, prefix in PREFIX.items()}


def mint(kind: TokenKind, entropy: bytes) -> str:
    """The token of `kind` made from exactly 32 random bytes."""
    if len(entropy) != ENTROPY_BYTES:
        msg = f"a token is made from {ENTROPY_BYTES} bytes of entropy, not {len(entropy)}"
        raise ValueError(msg)
    return PREFIX[kind] + base64.urlsafe_b64encode(entropy).decode().rstrip("=")


def kind_of(token: str) -> TokenKind | None:
    """The kind of a well formed token, `None` for anything else (no lookup is worth making)."""
    body = token[4:]
    if len(body) != ENCODED_LENGTH or not _ALPHABET.issuperset(body):
        return None
    return _BY_PREFIX.get(token[:4])


def digest(token: str) -> str:
    """What is stored: SHA-256 hex. A token has full entropy, so a fast unsalted hash is right."""
    return hashlib.sha256(token.encode()).hexdigest()


def expiry(now: datetime, lifetime: timedelta, kind: TokenKind) -> datetime:
    """When a token issued `now` ends; a lifetime outside what `kind` allows is refused."""
    if lifetime <= timedelta(0):
        raise BadRequestError("a token lifetime must be longer than zero")
    longest = LONGEST_LIFETIME[kind]
    if lifetime > longest:
        msg = f"a {kind.value} token lifetime is at most {longest}; ask for a shorter one"
        raise BadRequestError(msg)
    return now + lifetime


def check_label(label: str) -> str:
    """The name an owner token carries (`owner:<label>` is the author of what it writes)."""
    if not label.strip() or len(label) > MAX_LABEL or not label.isprintable():
        msg = f"a token label is one printable line of 1 to {MAX_LABEL} characters"
        raise BadRequestError(msg)
    return label
