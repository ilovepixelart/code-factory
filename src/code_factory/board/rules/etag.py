"""The tag an unchanged answer keeps."""

import hashlib
import json
from typing import Any

ETAG_DIGITS = 16


def body_of(answer: Any) -> str:  # noqa: ANN401
    """The compact JSON text of an answer: no spaces, Unicode kept, keys in the order given."""
    return json.dumps(answer, separators=(",", ":"), ensure_ascii=False)


def etag_of(body: str) -> str:
    """A quoted tag: the first 16 hex digits of the SHA-256 of the body's UTF-8 bytes."""
    return f'"{hashlib.sha256(body.encode()).hexdigest()[:ETAG_DIGITS]}"'
