"""A session's state from its captured events alone: the view the Sessions page draws.

`derive_unsettled` knows no clock; `settle.settled` applies it at read, so what is stored never
goes stale. A view is derived from the events since the latest `SessionStart` (the window); only
the working folder and the transcript reach back before it, which `carried` stands for.
"""

from collections.abc import Sequence

from code_factory.platform.text import scalar_text
from code_factory.sessions.models import (
    Action,
    AgentView,
    Event,
    SessionState,
    SessionView,
)
from code_factory.sessions.rules.events import text_field

# Bump when a rule here changes what a stored view holds: the startup check rebuilds old rows.
RULES_VERSION = 1
TOOL_RESULTS = ("PostToolUse", "PostToolUseFailure")
RESOLVES_PERMISSION = (*TOOL_RESULTS, "UserPromptSubmit", "Stop", "SessionEnd")
CLOSES_ACTIONS = ("UserPromptSubmit", "Stop")
SUMMARY_FIELDS = (
    "command",
    "file_path",
    "description",
    "pattern",
    "url",
    "notebook_path",
    "prompt",
)
TICKET_MARKER = ".code-factory/worktrees/"
# What of an event the views read: a window kept in memory holds only these payload keys.
VIEW_KEYS = frozenset(
    {"agent_type", "cwd", "prompt", "tool_input", "tool_name", "tool_use_id", "transcript_path"}
)

type Carried = tuple[str, str]


def clean(text: str) -> str:
    """Text a column can hold: a NUL becomes U+FFFD (Postgres refuses it), a lone surrogate `?`."""
    return text.replace("\x00", "\ufffd").encode("utf-8", errors="replace").decode("utf-8")


def shown(value: object) -> str | None:
    """A payload value as text: a scalar as `str()` gives it, a trimmed string its head and `…`."""
    if isinstance(value, dict):
        head = value.get("head")
        return f"{head}\u2026" if "_trimmed_chars" in value and isinstance(head, str) else None
    return None if value is None else scalar_text(value)


def field(event: Event, key: str) -> str:
    """A payload field as text, safe to store; empty when absent, null or not text."""
    return clean(shown(event.payload.get(key)) or "")


def for_views(event: Event) -> Event:
    """The event cut to the payload keys the views read."""
    kept = {key: value for key, value in event.payload.items() if key in VIEW_KEYS}
    return Event(
        event.seq,
        event.session_id,
        event.agent_id,
        event.name,
        event.captured_at,
        event.spool,
        event.offset,
        kept,
    )


def since_latest[T: Event](events: Sequence[T], name: str) -> Sequence[T] | None:
    """The events after the latest one called `name`; None when there is none."""
    for index in range(len(events) - 1, -1, -1):
        if events[index].name == name:
            return events[index + 1 :]
    return None


def session_state(current: Sequence[Event]) -> SessionState:
    """Ended, blocked on a permission, idle after a stop, or working."""
    if any(event.name == "SessionEnd" for event in current):
        return SessionState.ENDED
    asked = since_latest(current, "PermissionRequest")
    if asked is not None and not any(event.name in RESOLVES_PERMISSION for event in asked):
        return SessionState.BLOCKED
    stopped = since_latest(current, "Stop")
    if stopped is not None and not any(event.name == "UserPromptSubmit" for event in stopped):
        return SessionState.IDLE
    return SessionState.WORKING


def summary(tool_input: object) -> str:
    """The most telling field of a tool input; a trimmed value shows its head."""
    if not isinstance(tool_input, dict):
        return ""
    for name in SUMMARY_FIELDS:
        value = tool_input.get(name)
        if isinstance(value, str) and value:
            return clean(value)
        if isinstance(value, dict) and "_trimmed_chars" in value:
            head = value.get("head")
            if isinstance(head, str):
                return clean(f"{head}…")
    return ""


def _action_of(event: Event) -> Action:
    found = text_field(event.payload, "tool_use_id")
    return Action(
        tool=field(event, "tool_name"),
        summary=summary(event.payload.get("tool_input")),
        started_at=event.captured_at,
        tool_use_id=None if found is None else clean(found),
    )


def current_action(scope: Sequence[Event]) -> Action | None:
    """The newest tool call with no result yet, unless a prompt or a stop came after it."""
    answered: set[str | None] = set()
    for event in reversed(scope):
        if event.name in CLOSES_ACTIONS:
            return None
        if event.name in TOOL_RESULTS:
            answered.add(text_field(event.payload, "tool_use_id"))
        elif (
            event.name == "PreToolUse" and text_field(event.payload, "tool_use_id") not in answered
        ):
            return _action_of(event)
    return None


def last_call(scope: Sequence[Event]) -> Action | None:
    """The newest tool call, open or not."""
    for event in reversed(scope):
        if event.name == "PreToolUse":
            return _action_of(event)
    return None


def _item_text(item: object) -> str | None:
    content = item.get("content") if isinstance(item, dict) else None
    if isinstance(content, str):
        return clean(content)
    if isinstance(content, dict) and isinstance(content.get("head"), str):
        return clean(f"{content['head']}…")
    return None


def next_plan_item(scope: Sequence[Event]) -> str | None:
    """`plan 3/7: <item>` for the first item of the latest `TodoWrite` that is not completed."""
    written = next(
        (
            e
            for e in reversed(scope)
            if e.name == "PreToolUse" and field(e, "tool_name") == "TodoWrite"
        ),
        None,
    )
    if written is None:
        return None
    tool_input = written.payload.get("tool_input")
    items = tool_input.get("todos") if isinstance(tool_input, dict) else None
    if not isinstance(items, list):
        return None
    for at, item in enumerate(items):
        if not isinstance(item, dict) or item.get("status") != "completed":
            text = _item_text(item)
            return None if text is None else f"plan {at + 1}/{len(items)}: {text}"
    return None


def subagent_ticket(calls: Sequence[str]) -> str | None:
    """The ticket whose worktree the newest of an agent's tool calls names (newest first)."""
    for call in calls:
        _, found, after = call.partition(TICKET_MARKER)
        if not found:
            continue
        name = ""
        for char in after:
            if not (char.isascii() and (char.isalnum() or char in "-_")):
                break
            name += char
        if name:
            return name
    return None


def _scopes(events: Sequence[Event]) -> dict[str, list[Event]]:
    scopes: dict[str, list[Event]] = {}
    for event in events:
        if event.agent_id is not None:
            scopes.setdefault(event.agent_id, []).append(event)
    return scopes


def _subagent(agent_id: str, scope: list[Event]) -> AgentView:
    run = since_latest(scope, "SubagentStart")
    running = not any(event.name == "SubagentStop" for event in (scope if run is None else run))
    calls = [
        summary(event.payload.get("tool_input"))
        for event in reversed(scope)
        if event.name == "PreToolUse"
    ]
    started = next((e for e in reversed(scope) if e.name == "SubagentStart"), scope[0])
    typed = next((e for e in scope if "agent_type" in e.payload), None)
    return AgentView(
        agent_id=agent_id,
        agent_type="" if typed is None else field(typed, "agent_type"),
        running=running,
        current_action=current_action(scope) if running else None,
        last_event_at=scope[-1].captured_at,
        ticket=subagent_ticket(calls),
        started_at=started.captured_at,
    )


def _latest_field(events: Sequence[Event], key: str, carried: str) -> str:
    for event in reversed(events):
        if key in event.payload:
            return field(event, key)
    return carried


def carry(carried: Carried, events: Sequence[Event]) -> Carried:
    """`carried` moved on over `events`: the latest working folder and transcript they name."""
    return (
        _latest_field(events, "cwd", carried[0]),
        _latest_field(events, "transcript_path", carried[1]),
    )


def derive_unsettled(events: Sequence[Event], carried: Carried | None = None) -> SessionView | None:
    """The view of one session from its events, oldest first; None for no events.

    `carried` is the folder and transcript of the events before `events`, so that deriving a
    window gives what deriving everything would.
    """
    if not events:
        return None
    last = events[-1]
    after_start = since_latest(events, "SessionStart")
    current = events if after_start is None else after_start
    main = [event for event in current if event.agent_id is None]
    turn = since_latest(current, "UserPromptSubmit") or []
    prompt = next((e for e in reversed(current) if e.name == "UserPromptSubmit"), None)
    cwd, transcript = carry(carried or ("", ""), events)
    return SessionView(
        session_id=events[0].session_id,
        cwd=cwd,
        state=session_state(current),
        last_event_at=last.captured_at,
        current_action=current_action(main),
        subagents=[_subagent(agent, scope) for agent, scope in _scopes(current).items()],
        last_prompt="" if prompt is None else field(prompt, "prompt"),
        turn_started_at=None if prompt is None else prompt.captured_at,
        turn_tool_calls=sum(1 for event in turn if event.name == "PreToolUse"),
        transcript=transcript,
        plan=next_plan_item(main),
        last_call=last_call(main),
    )


def extend_window(
    window: Sequence[Event], carried: Carried, new: Sequence[Event]
) -> tuple[list[Event], Carried]:
    """The window after `new` events arrive, and what is carried from before it.

    A `SessionStart` among them starts a new window at the latest one; what the events before it
    name is carried. `carried` is what the stored view holds: the latest folder and transcript of
    everything so far.
    """
    starts = [at for at, event in enumerate(new) if event.name == "SessionStart"]
    if not starts:
        return [*window, *new], carried
    first = starts[-1]
    return list(new[first:]), carry(carried, new[:first])
