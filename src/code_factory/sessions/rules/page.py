"""The Sessions answers: one session as JSON, the list rows, and one filtered, counted page."""

from collections.abc import Callable, Iterable

from code_factory.platform.text import Paging, page_of
from code_factory.sessions.models import Action, SessionState, SessionView, StateFilter
from code_factory.sessions.rules.settle import doing

UNKNOWN_REPOSITORY = "unknown repository"
# The page draws one line of at most this many characters of a prompt or a tool summary.
LIST_TEXT_CHARS = 160


def state_of(view: SessionView) -> StateFilter | None:
    """The state a session counts under; none for an ended one."""
    if view.state == SessionState.BLOCKED:
        return StateFilter.WAITING
    if view.stale:
        return StateFilter.STALE
    return {SessionState.WORKING: StateFilter.WORKING, SessionState.IDLE: StateFilter.IDLE}.get(
        view.state
    )


def _action_json(action: Action | None, now: float) -> dict[str, object] | None:
    if action is None:
        return None
    return {
        "tool": action.tool,
        "summary": action.summary,
        "started_at": action.started_at,
        "elapsed_seconds": now - action.started_at,
        "tool_use_id": action.tool_use_id,
    }


def session_json(view: SessionView, now: float) -> dict[str, object]:
    """The JSON of one session as of `now` (the view is already settled)."""
    line, since = doing(view)
    return {
        "session_id": view.session_id,
        "cwd": view.cwd,
        "repository": view.repository,
        "branch": view.branch,
        "state": view.state.value,
        "last_event_at": view.last_event_at,
        "age_seconds": now - view.last_event_at,
        "stale": view.stale,
        "current_action": _action_json(view.current_action, now),
        "subagents": [
            {
                "agent_id": agent.agent_id,
                "agent_type": agent.agent_type,
                "running": agent.running,
                "stale": agent.stale,
                "current_action": _action_json(agent.current_action, now),
                "last_event_at": agent.last_event_at,
            }
            for agent in view.subagents
        ],
        "last_prompt": view.last_prompt,
        "turn_started_at": view.turn_started_at,
        "turn_tool_calls": view.turn_tool_calls,
        "doing": line,
        "doing_since": since,
    }


def _cut(text: str) -> str:
    if len(text) <= LIST_TEXT_CHARS:
        return text
    return f"{text[: LIST_TEXT_CHARS - 1]}…"


def _cut_action(action: object) -> None:
    if isinstance(action, dict):
        summary = action.get("summary")
        if isinstance(summary, str):
            action["summary"] = _cut(summary)
        action.pop("elapsed_seconds", None)


def list_json(view: SessionView, now: float) -> dict[str, object]:
    """A session as the list draws it: texts cut, and without the seconds counted since `now`.

    No row draws those seconds and they would change every answer.
    """
    row = session_json(view, now)
    row["last_prompt"] = _cut(view.last_prompt)
    row.pop("age_seconds")
    row["doing"] = _cut(str(row["doing"]))
    _cut_action(row["current_action"])
    subagents = row["subagents"]
    if isinstance(subagents, list):
        for agent in subagents:
            _cut_action(agent["current_action"])
    return row


def page_json(  # noqa: PLR0913  # the page's parameters are its query
    views: Iterable[SessionView],
    now: float,
    paging: Paging,
    *,
    ended: bool,
    state: StateFilter | None,
    ended_hidden: int,
    repository_of: Callable[[SessionView], str] = lambda view: view.repository,
) -> dict[str, object]:
    """One page of the list.

    `waiting` holds every blocked session, whole (none when `state` names another state).
    `rows` is the page of the rest: ended ones only when asked, `state` applied before paging,
    grouped by repository (the group with the newest activity first, attention order inside it).
    `counts` (per state) and `repositories` (rows per repository under `state`) cover the whole
    list, not the page. `ended_hidden` is how many ended sessions are left out.
    """
    views = list(views)
    blocked = [view for view in views if view.state == SessionState.BLOCKED]
    rest = [
        view
        for view in views
        if view.state != SessionState.BLOCKED and (ended or view.state != SessionState.ENDED)
    ]
    counts = {
        each.value: len(blocked)
        if each == StateFilter.WAITING
        else sum(1 for view in rest if state_of(view) == each)
        for each in StateFilter
    }
    groups: dict[str, list[SessionView]] = {}
    for view in rest:
        if state is None or state_of(view) == state:
            name = repository_of(view) or UNKNOWN_REPOSITORY
            groups.setdefault(name, []).append(view)
    by_activity = sorted(
        groups.items(), key=lambda item: max(v.last_event_at for v in item[1]), reverse=True
    )
    shown = [view for _, members in by_activity for view in members]
    show_waiting = state in (None, StateFilter.WAITING)
    answer: dict[str, object] = {
        "waiting": [list_json(view, now) for view in blocked] if show_waiting else [],
        "ended_hidden": 0 if ended else ended_hidden,
        "counts": counts,
        "repositories": {name: len(members) for name, members in by_activity},
    }
    return page_of(shown, paging).map(lambda view: list_json(view, now)).into_answer(answer, "rows")
