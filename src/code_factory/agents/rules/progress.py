"""What a running run has done so far, read from its own log.

Claude's stream JSON and codex's exec events. A number the log cannot give is `None`, never 0.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from code_factory.agents.models.progress import ChangedFiles, RunProgress, ToolCounts
from code_factory.agents.rules.logs import log_usage, records

NAMED_FILES = 10
# The records of each runtime that hold no tool call.
QUIET = (
    "system",
    "user",
    "result",
    "rate_limit_event",
    "error",
    "thread.started",
    "turn.started",
    "turn.completed",
    "turn.failed",
    "item.started",
)
READS = ("read", "grep", "glob", "ls", "list", "find", "search")
CHANGES = ("edit", "multiedit", "write", "notebookedit", "patch", "apply_patch", "file_change")
# Codex items that are what it said or planned, not a call.
SAID = ("agent_message", "reasoning", "todo_list", "error")


@dataclass(frozen=True)
class Call:
    """One tool call: its kind, what tells it from another call, and its id if it has one."""

    read: bool
    change: bool
    name: str
    signature: str
    call_id: str = ""


def _call(name: str, arguments: object, call_id: str = "", *, failed: bool = False) -> Call:
    lowered = name.lower()
    return Call(
        read=lowered in READS,
        change=lowered in CHANGES and not failed,
        name=name,
        signature=f"{name}\0{json.dumps(arguments, sort_keys=True)}",
        call_id=call_id,
    )


def _claude_calls(record: dict[str, Any]) -> list[Call] | None:
    """The `tool_use` blocks of an assistant message; `None` for one that cannot be read."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return None
    calls: list[Call] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name")
            if not isinstance(name, str):
                return None
            calls.append(_call(name, block.get("input"), str(block.get("id", ""))))
    return calls


def _codex_calls(record: dict[str, Any]) -> list[Call] | None:
    item = record.get("item")
    kind = item.get("type") if isinstance(item, dict) else None
    if not isinstance(item, dict) or not isinstance(kind, str):
        return None
    if kind in SAID:
        return []
    fields = {key: value for key, value in item.items() if key != "id"}
    failed = item.get("status") == "failed"
    return [_call(kind, fields, failed=failed)]


def _known(record: dict[str, Any]) -> bool:
    return record.get("type") in (*QUIET, "assistant", "item.completed")


def _calls_of(record: dict[str, Any]) -> list[Call] | None:
    """The calls a runtime's record holds; `None` for a tool record that cannot be read."""
    kind = record.get("type")
    if kind == "assistant":
        return _claude_calls(record)
    if kind == "item.completed":
        return _codex_calls(record)
    return []


def _refused(record: dict[str, Any]) -> list[str]:
    """The ids of the calls a user record says the tool refused."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if record.get("type") != "user" or not isinstance(content, list):
        return []
    return [
        str(block.get("tool_use_id"))
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "tool_result"
        and block.get("is_error") is True
    ]


class _Tally:
    """The running counts of `tool_counts`."""

    def __init__(self) -> None:
        self.total = self.reads = self.changes = self.repeated = 0
        self.last: Call | None = None
        self.changing: set[str] = set()

    def refuse(self, call_id: str) -> None:
        """Take back the change of a write the tool refused."""
        if call_id in self.changing:
            self.changing.discard(call_id)
            self.changes -= 1

    def add(self, call: Call) -> None:
        """Count `call`, a repeat when it is the call before it again."""
        self.total += 1
        again = self.last is not None and self.last.signature == call.signature
        self.repeated = self.repeated + 1 if again else 1
        self.last = call
        self.reads += call.read
        self.changes += call.change
        if call.change and call.call_id:
            self.changing.add(call.call_id)


def tool_counts(lines: Sequence[str]) -> ToolCounts | None:
    """The tool calls of a log: `None` when no record is a runtime's or a tool record is unreadable.

    A write the tool refused is a call and no change; a call is one of the repeats when it is the
    same tool with the same arguments as the call before it.
    """
    known = False
    tally = _Tally()
    for record in records(lines):
        for call_id in _refused(record):
            tally.refuse(call_id)
        if not _known(record):
            continue
        seen = _calls_of(record)
        if seen is None:
            return None
        known = True
        for call in seen:
            tally.add(call)
    if not known:
        return None
    return ToolCounts(
        calls=tally.total,
        reads=tally.reads,
        changes=tally.changes,
        repeated=tally.repeated,
        last_tool=tally.last.name if tally.last else "",
    )


def _message_tokens(found: list[dict[str, Any]]) -> int | None:
    """Claude's assistant messages, which hold a running run's tokens.

    One message has several lines, and its last holds its usage.
    """
    messages: dict[str, int] = {}
    for record in found:
        message = record.get("message")
        if record.get("type") != "assistant" or not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if isinstance(message.get("id"), str) and isinstance(usage, dict):
            messages[message["id"]] = sum(
                count
                for key in ("input_tokens", "output_tokens")
                if isinstance(count := usage.get(key), int) and not isinstance(count, bool)
            )
    return sum(messages.values()) if messages else None


def changed_files(changed: list[str], added: list[str]) -> ChangedFiles:
    """The files `changed` since a run's head and the `added` ones git does not track or ignore."""
    files = sorted({name for name in [*changed, *added] if name})
    return ChangedFiles(count=len(files), names=tuple(files[:NAMED_FILES]))


def run_progress(
    lines: Sequence[str] | None,
    reported_tokens: int | None,
    changed: ChangedFiles | None,
    last_activity: float | None,
) -> RunProgress:
    """What a run has done so far.

    `lines` are the log's, `None` when it cannot be read. Tokens are what the log reports, or what
    the run reported to the board when that is larger; an empty report is none.
    """
    counts = None if lines is None else tool_counts(lines)
    logged = None
    if lines is not None:
        logged = log_usage(lines).tokens
        if logged is None:
            logged = _message_tokens(records(lines))
    reported = reported_tokens or None
    known = [tokens for tokens in (logged, reported) if tokens is not None]
    return RunProgress(
        tool_calls=None if counts is None else counts.calls,
        reads=None if counts is None else counts.reads,
        changes=None if counts is None else counts.changes,
        files=changed,
        tokens=max(known) if known else None,
        last_activity=None if lines is None else last_activity,
    )
