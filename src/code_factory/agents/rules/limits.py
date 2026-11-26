"""A run that ended on its runtime's usage limit, and when a codex limit resets."""

import re
from typing import Any

from code_factory.agents.models.usage import Limit
from code_factory.agents.rules.logs import records

_LIMIT_WORDS = re.compile(
    r"\b(?:hit|reached) your\b.*?\blimit\b|usage limit|out of usage|quota exceeded"
    r"|exceeded your current quota|insufficient_quota",
    re.IGNORECASE,
)
_FULL = 100.0


def _worded(value: object) -> bool:
    return isinstance(value, str) and _LIMIT_WORDS.search(value) is not None


def _claude_limited(found: list[dict[str, Any]]) -> bool:
    last = next((r for r in reversed(found) if r.get("type") == "result"), None)
    return last is not None and last.get("is_error") is True and _worded(last.get("result"))


def _codex_message(record: dict[str, Any]) -> object | None:
    kind = record.get("type")
    if kind == "turn.failed":
        error = record.get("error")
        return error.get("message") if isinstance(error, dict) else None
    return record.get("message") if kind == "error" else None


def _codex_limited(found: list[dict[str, Any]]) -> bool:
    """Whether codex's last failure record is in a limit's words.

    A run that hit a limit, retried and then lost its stream failed for the stream; one that
    went on to complete a turn did not end on the limit.
    """
    for record in reversed(found):
        if record.get("type") == "turn.completed":
            return False
        if (said := _codex_message(record)) is not None:
            return _worded(said)
    return False


def _rejected_reset(found: list[dict[str, Any]]) -> float | None:
    for record in reversed(found):
        info = record.get("rate_limit_info")
        if record.get("type") == "rate_limit_event" and isinstance(info, dict):
            at = info.get("resetsAt")
            if info.get("status") == "rejected" and isinstance(at, int | float):
                return float(at)
    return None


def usage_limit(log: str) -> Limit | None:
    """The usage limit a run's log reports, if it ended on one.

    Claude's last result as an error in a limit's words, or codex's last failure record in a
    limit's words. The reset is a rejected `rate_limit_event`'s `resetsAt`; codex's run log states
    none (the board asks `codex app-server`, see `codex_reset`).
    """
    found = records(log.splitlines())
    if not (_claude_limited(found) or _codex_limited(found)):
        return None
    return Limit(reset=_rejected_reset(found))


def codex_reset(line: str) -> float | None:
    """When the codex limit an `account/rateLimits/read` answer reports resets.

    The earliest `resetsAt` of the `primary` or `secondary` window at 100 percent or more, in
    epoch seconds; `None` when the line is no such answer, no window is full, or a full window
    states no reset.
    """
    found = records([line])
    result = found[0].get("result") if found else None
    limits = result.get("rateLimits") if isinstance(result, dict) else None
    if not isinstance(limits, dict):
        return None
    resets = [
        float(window["resetsAt"])
        for name in ("primary", "secondary")
        if isinstance(window := limits.get(name), dict)
        and isinstance(used := window.get("usedPercent"), int | float)
        and used >= _FULL
        and isinstance(window.get("resetsAt"), int | float)
    ]
    return min(resets) if resets else None
