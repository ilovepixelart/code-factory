"""What a spool line becomes in the ledger: an event row, or a reject that is kept and skipped."""

import json
import math

from code_factory.platform.text import scalar_text
from code_factory.sessions.models import NewEvent, Reject

HEAD_BYTES = 200
EPOCH_LAST = 253402300799  # 9999-12-31T23:59:59Z, the last second `timestamptz` holds
TOO_LONG = "line too long"
NOT_STORABLE = "a text field holds a NUL or a lone surrogate"
# A btree row holds 2,704 bytes: the session id sits in two indexes, with the sequence beside it.
MOST_SESSION_ID_BYTES = 1024
SESSION_ID_TOO_LONG = f"the session id is over {MOST_SESSION_ID_BYTES} bytes"


def captured_at(payload: dict[str, object]) -> float:
    """`_captured_at` as seconds since the epoch; 0 when absent, not a number or out of range."""
    value = payload.get("_captured_at")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    if not 0 <= value <= EPOCH_LAST:
        return 0.0
    return float(value)


def text_field(payload: dict[str, object], key: str) -> str | None:
    """A payload field as `str()` gives it; None when absent, null or not a scalar."""
    value = payload.get(key)
    return None if value is None else scalar_text(value)


def _storable(text: str) -> bool:
    """Whether a `text` column can hold it: no NUL, no lone surrogate (that is no UTF-8)."""
    if "\x00" in text:
        return False
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _head(line: bytes) -> str:
    return line[:HEAD_BYTES].decode("utf-8", errors="replace").replace("\x00", "\ufffd")


def _no_constant(name: str) -> object:
    msg = f"{name} is not a number the ledger can store"
    raise ValueError(msg)


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        msg = f"{text} is not a number the ledger can store"
        raise ValueError(msg)
    return value


def event_row(spool: str, offset: int, line: bytes) -> NewEvent | Reject:
    """The row the line at `offset` of `spool` makes, or the reject saying why it is none."""
    try:
        parsed = json.loads(line.decode("utf-8"), parse_constant=_no_constant, parse_float=_finite)
    except (ValueError, RecursionError) as error:
        return Reject(spool, offset, f"{type(error).__name__}: {error}", _head(line))
    if not isinstance(parsed, dict):
        return Reject(spool, offset, "not a JSON object", _head(line))
    session_id = text_field(parsed, "session_id") or ""
    agent_id = text_field(parsed, "agent_id")
    event = text_field(parsed, "hook_event_name") or ""
    if not all(_storable(text) for text in (session_id, agent_id or "", event)):
        return Reject(spool, offset, f"ValueError: {NOT_STORABLE}", _head(line))
    if len(session_id.encode("utf-8")) > MOST_SESSION_ID_BYTES:
        return Reject(spool, offset, f"ValueError: {SESSION_ID_TOO_LONG}", _head(line))
    return NewEvent(spool, offset, session_id, agent_id, event, captured_at(parsed), parsed)


def too_long(spool: str, offset: int, head: bytes) -> Reject:
    """The reject of a line past the length limit, which is never read whole."""
    return Reject(spool, offset, TOO_LONG, _head(head))
