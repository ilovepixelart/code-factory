"""The capture hook: records one agent hook payload in the session spool, never printing or failing.

The agent runs this file by path (`python -I -S capture.py`) on every hook event, so it imports
only the standard library: importing the package would cost more than the hook budget, and the
interpreter start is the floor. The secret patterns therefore exist twice (here and in
`platform.text.masking`); a test holds them equal.

The owner's context never reaches the spool: the board publishes `redaction.json` in the state
folder, and a run that names a context (`CODE_FACTORY_CONTEXT`) the file does not list keeps
nothing of its payload.
"""

import json
import math
import os
import re
import sys
import time
from collections import namedtuple

TRIM_LIMIT = 2000
HEAD_CHARS = 200
PAYLOAD_HEAD_BYTES = 200
# Enough to see what a failed payload began with; the masking is not run over a megabyte.
HEAD_SCAN_CHARS = 4096
REDACTED = "[redacted]"
UNIDENTIFIED_SPOOL = "_unidentified.jsonl"
CONTEXT_VARIABLE = "CODE_FACTORY_CONTEXT"
STATE_DIR_VARIABLE = "CODE_FACTORY_STATE_DIR"
REDACTION_FILE = "redaction.json"
ERROR_LOG = "capture-errors.log"
_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
# A value under a key that names a secret is one, whatever it looks like: `{"password": "x"}`
# has no `password=` in front of the value for the text patterns to see.
_SECRET_KEY = re.compile(
    r"(?:[a-z0-9]+[_-])*(?:api[_-]?key|token|secret|password|passwd|authorization)", re.IGNORECASE
)
# The line the gate prints for a failed step: the one thing recurring failures need from a
# tool output that is too long to keep.
_GATE_LINE = re.compile(r"gate: [a-z0-9-]+ failed \(exit [0-9]{1,3}\)")
MOST_GATE_LINES = 20

_KEY_END = r"""\\*["']?\s*[=:]\s*"""
_QUOTED_VALUE = (
    r"""(")(?:[^"\\]|\\.)+"""
    r"""|(?P<esc>\\+")(?:[^"\\]|\\++(?!")|(?!(?P=esc))\\++")+"""
    r"""|(')(?:[^'\\]|\\.)+"""
)
_AUTH_WORD = r"""(?:[^\s"'\\]|\\+[^\s"'\\])+"""
_BARE_VALUE = r"""(?:[^\s"',;\\]|\\+[^\s"',;\\])+"""
_PATTERNS = (
    re.compile(
        rf"(authorization{_KEY_END})(?:{_QUOTED_VALUE}|{_AUTH_WORD}(?:\s+{_AUTH_WORD})?)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"((?:api[_-]?key|token|secret|password|passwd){_KEY_END})(?:{_QUOTED_VALUE}|{_BARE_VALUE})",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:sk-|ghp_|gho_|xoxb-|xoxp-)[A-Za-z0-9_-]+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


# The spool file name and the line to append for a payload; why a payload has no record
# (`<ErrorType>: <message>`). Plain named tuples: `typing` is not worth its import time here.
Record = namedtuple("Record", ["spool", "line"])  # noqa: PYI024
Refused = namedtuple("Refused", ["reason"])  # noqa: PYI024


class ContextUnavailableError(Exception):
    """The run names an owner context that the redaction file does not list."""


def _mask_match(found: re.Match[str]) -> str:
    kept = "".join(group for group in found.groups() if group is not None)
    return kept + REDACTED


def mask(text: str) -> str:
    """The text with the value of every secret key and every known key shape replaced."""
    for pattern in _PATTERNS:
        text = pattern.sub(_mask_match, text)
    return text


def apply_redaction[T: (str, bytes)](value: T, patterns: list[tuple[str, str]]) -> T:
    """The value with each find replaced in turn, in the order given (longest first)."""
    for find, replacement in patterns:
        if isinstance(value, bytes):
            value = value.replace(find.encode(), replacement.encode())  # ty: ignore[invalid-assignment]  # T is bytes here
        else:
            value = value.replace(find, replacement)  # ty: ignore[invalid-assignment]  # T is str here
    return value


def _gate_lines(text: str) -> list[str]:
    found = (line.strip() for line in text.split("\n"))
    return list(dict.fromkeys(line for line in found if _GATE_LINE.fullmatch(line)))[
        :MOST_GATE_LINES
    ]


def _trimmed(text: str) -> dict[str, object]:
    marker: dict[str, object] = {"_trimmed_chars": len(text), "head": text[:HEAD_CHARS]}
    gates = _gate_lines(text)
    if gates:
        marker["gates"] = gates
    return marker


def _sanitized(value: object, patterns: list[tuple[str, str]] | None) -> object:
    match value:
        case str():
            text = mask(apply_redaction(value, patterns or []))
            return _trimmed(text) if len(text) > TRIM_LIMIT else text
        case dict():
            return {
                key: REDACTED
                if isinstance(item, str) and _SECRET_KEY.fullmatch(key)
                else _sanitized(item, patterns)
                for key, item in value.items()
            }
        case list():
            return [_sanitized(item, patterns) for item in value]
        case _:
            return value


def _spool_name(session_id: object) -> str:
    if isinstance(session_id, str) and _SESSION_ID.fullmatch(session_id):
        return f"{session_id}.jsonl"
    return UNIDENTIFIED_SPOOL


def _no_constant(name: str) -> object:
    msg = f"{name} is not a number the ledger can store"
    raise ValueError(msg)


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        msg = f"{text} is not a number the ledger can store"
        raise ValueError(msg)
    return value


def _reason(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


def record(
    raw: bytes, now: float, redaction: list[tuple[str, str]] | None = None
) -> Record | Refused:
    """The record of a payload captured at `now`, its strings through `redaction`."""
    try:
        text = apply_redaction(raw, redaction or []).decode("utf-8")
        parsed = json.loads(text, parse_constant=_no_constant, parse_float=_finite)
        if not isinstance(parsed, dict):
            return Refused("TypeError: payload is not a JSON object")
    except (ValueError, RecursionError) as error:  # JSONDecodeError and UnicodeDecodeError
        return Refused(_reason(error) if isinstance(error, ValueError) else "RecursionError")
    payload = _sanitized(parsed, redaction)
    if not isinstance(payload, dict):  # a dict goes in, a dict comes out
        return Refused("TypeError: payload is not a JSON object")
    payload["_captured_at"] = now
    line = json.dumps(payload, separators=(",", ":")) + "\n"
    return Record(_spool_name(payload.get("session_id")), line)


def _safe_head(raw: bytes, redaction: list[tuple[str, str]] | None) -> bytes:
    """The start of a payload as the error log may hold it: owner context and secrets removed."""
    text = apply_redaction(raw, redaction or []).decode("utf-8", errors="replace")
    return mask(text[:HEAD_SCAN_CHARS]).encode("utf-8")


def failure_entry(reason: str, raw: bytes, now: float) -> str:
    """The line the error log gets for a payload that was not recorded."""
    head = raw[:PAYLOAD_HEAD_BYTES].decode("utf-8", errors="replace")
    return json.dumps({"at": now, "reason": reason, "payload_head": head}) + "\n"


def read_redaction(path: str, reference: str | None) -> list[tuple[str, str]] | None:
    """The patterns of the redaction file; fails closed when `reference` is not listed in it."""
    try:
        with open(path, "rb") as handle:  # noqa: PTH123  # stdlib only, no pathlib import cost
            data = json.loads(handle.read())
        references = list(data["references"])
        patterns = [(str(find), str(replacement)) for find, replacement in data["patterns"]]
    except OSError, ValueError, KeyError, TypeError:
        if reference is None:
            return None
        raise ContextUnavailableError(reference) from None
    if reference is not None and reference not in references:
        raise ContextUnavailableError(reference)
    return patterns or None


def _append(path: str, data: bytes) -> None:
    """One `O_APPEND` write, so concurrent hooks never interleave their lines."""
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(descriptor, view) :]
    finally:
        os.close(descriptor)


def _state_dir() -> str:
    configured = os.environ.get(STATE_DIR_VARIABLE)
    return configured or os.path.join(os.path.expanduser("~"), ".local", "state", "code-factory")  # noqa: PTH118, PTH111


def capture(raw: bytes, now: float, state_dir: str) -> None:
    """Append the payload to its session's spool, or the failure to the error log."""
    reference = os.environ.get(CONTEXT_VARIABLE) or None
    try:
        redaction = read_redaction(os.path.join(state_dir, REDACTION_FILE), reference)  # noqa: PTH118
    except ContextUnavailableError:
        _log_failure(state_dir, f"the owner's context {reference} cannot be read", b"", now)
        return
    try:
        result = record(raw, now, redaction)
        if isinstance(result, Refused):
            _log_failure(state_dir, result.reason, _safe_head(raw, redaction), now)
            return
        spool = os.path.join(state_dir, "spool")  # noqa: PTH118
        os.makedirs(spool, mode=0o700, exist_ok=True)  # noqa: PTH103
        _append(os.path.join(spool, result.spool), result.line.encode("ascii"))  # noqa: PTH118
    except Exception as error:  # noqa: BLE001  # the hook must never fail the agent
        _log_failure(state_dir, f"{type(error).__name__}: {error}", _safe_head(raw, redaction), now)


def _log_failure(state_dir: str, reason: str, raw: bytes, now: float) -> None:
    try:
        os.makedirs(state_dir, mode=0o700, exist_ok=True)  # noqa: PTH103
        _append(os.path.join(state_dir, ERROR_LOG), failure_entry(reason, raw, now).encode())  # noqa: PTH118
    except Exception:  # noqa: BLE001, S110  # nothing is left to report to
        pass


def main() -> None:
    """The hook: read the payload from standard input, record it, say nothing, exit 0."""
    try:
        raw = sys.stdin.buffer.read()
    except Exception:  # noqa: BLE001  # an unreadable stdin records nothing
        raw = b""
    capture(raw, time.time(), _state_dir())


if __name__ == "__main__":
    main()
