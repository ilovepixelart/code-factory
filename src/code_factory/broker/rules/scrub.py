"""Taking a secret out of what the provider said."""

import json
import zlib
from collections.abc import Iterable

from code_factory.broker.rules.headers import MIN_SECRET

REDACTED = b"[redacted]"
ERROR_BODY_LIMIT = 256 * 1024
_MIN_PARTIAL = 4
_DECODABLE = frozenset({"gzip", "x-gzip", "deflate"})


def _spellings(secret: str) -> set[bytes]:
    """The secret raw and as it reads inside a JSON string."""
    raw = secret.encode()
    return {
        raw,
        json.dumps(secret)[1:-1].encode(),
        json.dumps(secret, ensure_ascii=False)[1:-1].encode(),
    }


def _all_spellings(secrets: Iterable[str]) -> list[bytes]:
    found: set[bytes] = set()
    for secret in secrets:
        if len(secret.encode()) >= MIN_SECRET:
            found |= _spellings(secret)
    return sorted(found, key=len, reverse=True)


def scrub(data: bytes, secrets: Iterable[str]) -> bytes:
    """`data` with every occurrence of each secret of at least 8 bytes replaced, longest first."""
    for spelling in _all_spellings(secrets):
        data = data.replace(spelling, REDACTED)
    return data


def _without_partial_tail(data: bytes, spellings: list[bytes]) -> bytes:
    """`data` without a trailing start of a secret that the cut may have split."""
    for spelling in spellings:
        for size in range(min(len(spelling) - 1, len(data)), _MIN_PARTIAL - 1, -1):
            if data.endswith(spelling[:size]):
                return data[:-size]
    return data


def _decoded(encoding: str, data: bytes) -> bytes | None:
    """The body undone from its encoding, at most one byte over the limit; `None` if it cannot."""
    if encoding in ("", "identity"):
        return data[: ERROR_BODY_LIMIT + 1]
    if encoding not in _DECODABLE:
        return None
    try:
        return zlib.decompressobj(zlib.MAX_WBITS | 32).decompress(data, ERROR_BODY_LIMIT + 1)
    except zlib.error:
        return None


def error_body(encoding: str | None, data: bytes, secrets: Iterable[str]) -> bytes | None:
    """What may be shown of an error body: decoded, cut at 256 KiB and scrubbed.

    `None` when the encoding is one the broker cannot undo, since a key inside it could not be
    found. A cut body also loses a trailing part of a secret that the cut split.
    """
    plain = _decoded((encoding or "").strip().lower(), data)
    if plain is None:
        return None
    spellings = _all_spellings(secrets)
    cut = len(plain) > ERROR_BODY_LIMIT
    shown = scrub(plain[:ERROR_BODY_LIMIT], secrets)
    return _without_partial_tail(shown, spellings) if cut else shown
