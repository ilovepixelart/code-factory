"""Conditional requests (RFC 9110 section 13.1): ETags, If-None-Match and If-Match.

An ETag per answer and 304 to a matching If-None-Match; the If-Match test a write makes against
the state it was read at.

`If-None-Match` is compared weakly (a `W/` prefix is ignored on both sides), may list several
tags separated by commas, and `*` matches any current answer.
"""

import hashlib
import json
from typing import Any

from fastapi import Request
from fastapi.responses import Response

ETAG_DIGITS = 16


def etag_of(body: str) -> str:
    """A strong tag of the answer's bytes."""
    return f'"{hashlib.sha256(body.encode()).hexdigest()[:ETAG_DIGITS]}"'


def tag_of(content: Any) -> str:  # noqa: ANN401  # any JSON value
    """A strong tag of a JSON value: the same value always gives the same tag."""
    return etag_of(json.dumps(content, ensure_ascii=False, allow_nan=False, sort_keys=True))


def _opaque(tag: str) -> str:
    return tag.strip().removeprefix("W/")


def matches(if_none_match: str | None, etag: str) -> bool:
    """Whether the request's `If-None-Match` names this answer's tag (weak comparison)."""
    if if_none_match is None or not if_none_match.strip():
        return False
    tags = [part.strip() for part in if_none_match.split(",")]
    return "*" in tags or _opaque(etag) in {_opaque(tag) for tag in tags}


def still_matches(if_match: str | None, etag: str) -> bool:
    """Whether a write may go ahead under `If-Match`: absent, `*`, or naming this tag strongly.

    RFC 9110 section 13.1.1: a weak tag (`W/`) never matches for `If-Match`.
    """
    if if_match is None:
        return True
    tags = [part.strip() for part in if_match.split(",")]
    return "*" in tags or etag in tags


def conditional_json(request: Request, body: str) -> Response:
    """The JSON answer with its ETag, or 304 with no body when the client holds it already."""
    etag = etag_of(body)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)
