"""One session's timeline: its lines, the outcome of each tool call and the payloads of one call."""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from code_factory.sessions.models import Event
from code_factory.sessions.rules.derive import CLOSES_ACTIONS, TOOL_RESULTS, field, summary
from code_factory.sessions.rules.events import text_field


@dataclass(frozen=True, slots=True)
class Entry:
    """One line of a session's timeline."""

    kind: str
    seq: int
    at: float
    agent_id: str | None
    title: str
    detail: str
    duration_seconds: float | None
    status: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool call's payloads as the ledger stores them."""

    tool: str
    input: object
    output: object | None


_PLAIN = {
    "SessionStart": ("session_start", "Session started", "source"),
    "SessionEnd": ("session_end", "Session ended", "reason"),
    "UserPromptSubmit": ("prompt", "Prompt", "prompt"),
    "Stop": ("stop", "Turn ended", "last_assistant_message"),
    "Notification": ("notification", "notification_type", "message"),
    "SubagentStart": ("subagent_start", "agent_type", ""),
    "SubagentStop": ("subagent_stop", "agent_type", ""),
}


def _plain_entry(event: Event) -> Entry | None:
    found = _PLAIN.get(event.name)
    if found is None:
        return None
    kind, title, detail_field = found
    if title in event.payload:
        title = text_field(event.payload, title) or title
    return Entry(
        kind=kind,
        seq=event.seq,
        at=event.captured_at,
        agent_id=event.agent_id,
        title=title,
        detail=field(event, detail_field) if detail_field else "",
        duration_seconds=None,
        status="",
    )


def _duration(call: Event, result: Event) -> float:
    ms = result.payload.get("duration_ms")
    if isinstance(ms, int | float) and not isinstance(ms, bool):
        return ms / 1000.0
    return result.captured_at - call.captured_at


def _status(result: Event | None, *, permission: bool, closed: bool) -> str:
    if result is not None:
        return "failed" if result.name == "PostToolUseFailure" else "done"
    if closed:
        return "denied" if permission else "interrupted"
    return "waiting" if permission else "running"


def outcome_of(events: Sequence[Event], index: int) -> tuple[Event | None, str]:
    """The result event of the call at `events[index]` and its status, by scanning forward.

    Only the later events of the same agent count. A prompt or a stop closes the turn: a result
    after it is not this call's, and a call with none was interrupted (denied when a permission
    for its tool was asked). Linear per call; `timeline` computes every call in one pass.
    """
    call = events[index]
    call_id = text_field(call.payload, "tool_use_id")
    name = text_field(call.payload, "tool_name")
    later = [event for event in events[index + 1 :] if event.agent_id == call.agent_id]
    result = None
    for event in later:
        if event.name in CLOSES_ACTIONS:
            break
        if event.name in TOOL_RESULTS and text_field(event.payload, "tool_use_id") == call_id:
            result = event
            break
    if result is not None:
        return result, _status(result, permission=False, closed=False)
    permission = False
    for event in later:
        if event.name == "PermissionRequest" and text_field(event.payload, "tool_name") == name:
            permission = True
        if event.name in CLOSES_ACTIONS or event.name == "SubagentStop":
            return None, _status(None, permission=permission, closed=True)
    return None, _status(None, permission=permission, closed=False)


@dataclass(slots=True)
class _Stream:
    """One agent's events with what answers a call's outcome by position, not by scanning."""

    events: list[Event]
    closes: list[int]
    stops: list[int]
    results: dict[str | None, list[int]]
    permissions: dict[str | None, list[int]]

    @classmethod
    def of(cls, events: list[Event]) -> _Stream:
        stream = cls(events, [], [], {}, {})
        for at, event in enumerate(events):
            if event.name in CLOSES_ACTIONS:
                stream.closes.append(at)
            if event.name in CLOSES_ACTIONS or event.name == "SubagentStop":
                stream.stops.append(at)
            if event.name in TOOL_RESULTS:
                stream.results.setdefault(text_field(event.payload, "tool_use_id"), []).append(at)
            if event.name == "PermissionRequest":
                stream.permissions.setdefault(text_field(event.payload, "tool_name"), []).append(at)
        return stream

    def _next(self, positions: list[int], after: int) -> int | None:
        found = bisect_right(positions, after)
        return positions[found] if found < len(positions) else None

    def outcome(self, at: int) -> tuple[Event | None, str]:
        """The same answer as `outcome_of`, in logarithmic time."""
        call = self.events[at]
        close = self._next(self.closes, at)
        found = self._next(self.results.get(text_field(call.payload, "tool_use_id"), []), at)
        if found is not None and (close is None or found < close):
            result = self.events[found]
            return result, _status(result, permission=False, closed=False)
        stop = self._next(self.stops, at)
        asked = self._next(self.permissions.get(text_field(call.payload, "tool_name"), []), at)
        permission = asked is not None and (stop is None or asked < stop)
        return None, _status(None, permission=permission, closed=stop is not None)


def timeline(events: Sequence[Event]) -> list[Entry]:
    """The timeline of one session, oldest first."""
    streams: dict[str | None, list[Event]] = {}
    for event in events:
        streams.setdefault(event.agent_id, []).append(event)
    built = {agent: _Stream.of(stream) for agent, stream in streams.items()}
    positions = dict.fromkeys(streams, 0)
    entries = []
    for event in events:
        at = positions[event.agent_id]
        positions[event.agent_id] = at + 1
        if event.name != "PreToolUse":
            entry = _plain_entry(event)
            if entry is not None:
                entries.append(entry)
            continue
        result, status = built[event.agent_id].outcome(at)
        entries.append(
            Entry(
                kind="tool",
                seq=event.seq,
                at=event.captured_at,
                agent_id=event.agent_id,
                title=field(event, "tool_name"),
                detail=summary(event.payload.get("tool_input")),
                duration_seconds=None if result is None else _duration(event, result),
                status=status,
            )
        )
    return entries


def window(entries: Sequence[Entry], last: int) -> tuple[Sequence[Entry], int]:
    """The latest `last` entries, and how many prompts come before them."""
    cut = max(len(entries) - last, 0)
    return entries[cut:], sum(1 for entry in entries[:cut] if entry.kind == "prompt")


def tool_call(events: Sequence[Event], seq: int) -> ToolCall | None:
    """The call the `PreToolUse` event `seq` made; None when `seq` is no such event."""
    index = next(
        (at for at, e in enumerate(events) if e.seq == seq and e.name == "PreToolUse"), None
    )
    if index is None:
        return None
    call = events[index]
    result, _ = outcome_of(events, index)
    output = None
    if result is not None:
        output = result.payload.get(
            "error" if result.name == "PostToolUseFailure" else "tool_response"
        )
    return ToolCall(field(call, "tool_name"), call.payload.get("tool_input"), output)


def entry_json(entry: Entry) -> dict[str, object]:
    """The JSON of one timeline entry."""
    return {
        "kind": entry.kind,
        "seq": entry.seq,
        "at": entry.at,
        "agent_id": entry.agent_id,
        "title": entry.title,
        "detail": entry.detail,
        "duration_seconds": entry.duration_seconds,
        "status": entry.status,
    }
