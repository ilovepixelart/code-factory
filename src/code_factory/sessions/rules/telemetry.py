"""The request events a run's OpenTelemetry export sends to the board."""

from code_factory.sessions.models import Request

# A model's whole context is far below it, and it keeps any sum of a run's requests within int64.
MOST_PER_REQUEST = 100_000_000
# An int64 has 19 digits; a longer string is no count and would hit the interpreter's digit limit.
MOST_DIGITS = 19
REQUEST_EVENT = "claude_code.api_request"


def _list(value: object, key: str) -> list[object]:
    found = value.get(key) if isinstance(value, dict) else None
    return [*found] if isinstance(found, list) else []


def _attribute(record: object, key: str) -> object:
    for item in _list(record, "attributes"):
        if isinstance(item, dict) and item.get("key") == key:
            return item.get("value")
    return None


def count(value: object) -> int | None:
    """A count as OTLP JSON writes a 64-bit integer, a number or a decimal string.

    Within `MOST_PER_REQUEST`; None for anything else (negative, fractional, text with letters).
    """
    raw = value.get("intValue") if isinstance(value, dict) else None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        found = raw
    elif isinstance(raw, str) and len(raw) <= MOST_DIGITS and raw.isascii() and raw.isdigit():
        found = int(raw)
    else:
        return None
    return found if 0 <= found <= MOST_PER_REQUEST else None


def _request(record: object) -> Request | None:
    named = record.get("body") if isinstance(record, dict) else None
    if not isinstance(named, dict) or named.get("stringValue") != REQUEST_EVENT:
        return None
    tokens = count(_attribute(record, "input_tokens"))
    output = count(_attribute(record, "output_tokens"))
    return Request(tokens, output) if tokens is not None and output is not None else None


def requests(body: object) -> list[Request]:
    """The `claude_code.api_request` events of an OTLP JSON logs export with both counts readable.

    Whatever run they claim, they count for the run whose token sent them.
    """
    records = (
        record
        for resource in _list(body, "resourceLogs")
        for scope in _list(resource, "scopeLogs")
        for record in _list(scope, "logRecords")
    )
    return [found for record in records if (found := _request(record)) is not None]
