"""The tokens a session spent and the cost its agent runtime reported, read from transcripts.

Each assistant message id counts once (its last record), synthetic and id-less messages are left
out, subagent transcripts add their tokens, and the latest `cost-state` record of the session's own
transcript is the cost. Nothing here estimates a price.
"""

import json
from collections.abc import Iterable
from dataclasses import replace
from pathlib import PurePosixPath

from code_factory.platform.text import scalar_text
from code_factory.sessions.models import Usage

_INT64 = 2**63


def _number(value: object) -> int:
    """A token count as the transcript writes it: an integer (`true` is 1), else zero."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and -_INT64 <= value < _INT64:
        return value
    return 0


def _message_tokens(record: dict[str, object]) -> tuple[str, tuple[int, int, int, int]] | None:
    """The id and the four token counts of a record's message; None when it counts for nothing."""
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    tokens = message.get("usage")
    if not isinstance(tokens, dict):
        return None
    if message.get("model") == "<synthetic>" or not message.get("id"):
        return None
    message_id = scalar_text(message["id"])
    if message_id is None:
        return None
    counts = (
        _number(tokens.get("input_tokens")),
        _number(tokens.get("output_tokens")),
        _number(tokens.get("cache_read_input_tokens")),
        _number(tokens.get("cache_creation_input_tokens")),
    )
    return message_id, counts


class Totals:
    """One transcript's tokens per distinct message and its latest cost report.

    Folded in line by line, so that a transcript that grew is read from where it was read to.
    """

    def __init__(self) -> None:
        self._messages: dict[str, tuple[int, int, int, int]] = {}
        self._cost: float | None = None
        self._reported_at: float | None = None
        self._incomplete = False

    def absorb_text(self, text: str) -> int:
        """Fold in the lines of `text`, which starts at a line start; the bytes consumed.

        A record ends at a newline and nowhere else (a JSON string may hold any other separator).
        Every line ended by one is consumed, and a last line without one only when it is a whole
        JSON object: a line still being written is read again once it is complete.
        """
        *complete, tail = text.split("\n")
        consumed = 0
        for line in complete:
            self._absorb(line)
            consumed += len(line) + 1
        if tail and self._absorb(tail):
            consumed += len(tail)
        return len(text[:consumed].encode("utf-8"))

    def _absorb(self, line: str) -> bool:
        try:
            record = json.loads(line)
        except ValueError, RecursionError:
            return False
        if not isinstance(record, dict):
            return False
        cost = record.get("totalCostUSD")
        if record.get("type") == "cost-state" and isinstance(cost, int | float):
            ended = _number(record.get("startTime")) + _number(record.get("totalDuration"))
            self._cost = float(cost)
            self._reported_at = ended / 1000.0
            self._incomplete = bool(record.get("hasUnknownModelCost"))
        found = _message_tokens(record)
        if found is not None:
            self._messages[found[0]] = found[1]
        return True

    def usage(self) -> Usage:
        """The tokens of the messages folded in, each distinct id once, and the latest cost."""
        totals = [sum(counts[at] for counts in self._messages.values()) for at in range(4)]
        return Usage(
            input=totals[0],
            output=totals[1],
            cache_read=totals[2],
            cache_write=totals[3],
            cost=self._cost,
            reported_at=self._reported_at,
            cost_incomplete=self._incomplete,
        )


def transcript_files(names: Iterable[str], transcript: str) -> list[str]:
    """The transcripts a session's usage reads: its own, then its subagents' in name order.

    `names` is what the folder `<transcript without extension>/subagents` holds. None without a
    transcript.
    """
    if not transcript:
        return []
    folder = PurePosixPath(transcript).with_suffix("") / "subagents"
    return [transcript, *(str(folder / name) for name in sorted(names) if name.endswith(".jsonl"))]


def summed(usages: Iterable[Usage]) -> Usage:
    """A session's usage from its transcripts' usages, its own first.

    The subagents add their tokens; the cost is the session's own.
    """
    usages = list(usages)
    if not usages:
        return Usage()
    total = usages[0]
    for sub in usages[1:]:
        total = replace(
            total,
            input=total.input + sub.input,
            output=total.output + sub.output,
            cache_read=total.cache_read + sub.cache_read,
            cache_write=total.cache_write + sub.cache_write,
        )
    return total
