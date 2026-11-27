"""The event stream's frames and the position a reader resumes after."""

import re

from code_factory.platform.text import render
from code_factory.sessions.models import Event

KEEPALIVE = ": keepalive\n\n"
_INT64 = 2**63
_INTEGER = re.compile(r"[+-]?\d+", re.ASCII)


def event_json(event: Event) -> dict[str, object]:
    """The JSON a stream sends for one event."""
    return {
        "seq": event.seq,
        "session_id": event.session_id,
        "agent_id": event.agent_id,
        "event": event.name,
        "captured_at": event.captured_at,
        "payload": event.payload,
    }


def sse_frame(event: Event) -> str:
    """One server-sent event: `id: <seq>` and the event as `data`."""
    return f"id: {event.seq}\ndata: {render(event_json(event))}\n\n"


def position(after: str | None, last_event_id: str | None) -> int | None:
    """The `seq` a stream resumes after: `after`, else `Last-Event-ID`, else 0.

    An empty value counts as absent. None when the one that applies is not an integer.
    """
    chosen = next(
        (value for value in (after, last_event_id) if value is not None and value != ""), None
    )
    if chosen is None:
        return 0
    text = chosen.strip()
    if _INTEGER.fullmatch(text) is None or not -_INT64 <= int(text) < _INT64:
        return None
    return int(text)
