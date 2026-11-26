"""What the clock adds to a stored view: ended, stale, and the order that draws attention."""

from collections.abc import Iterable

from code_factory.sessions.models import SessionState, SessionView

STALE_AFTER_SECONDS = 600.0
ENDED_AFTER_SECONDS = 3600.0


def settled(view: SessionView, now: float) -> SessionView:
    """The view as of `now`.

    A working or idle session with no event for 3600 s has ended; a working one with none for
    600 s is stale. A subagent with none for 3600 s no longer runs; a running one whose open call
    has had none for 600 s is stale, and one that is stale or stopped has no current action.
    Blocked never ends by the clock.
    """
    quiet = now - view.last_event_at
    state = view.state
    if state in (SessionState.WORKING, SessionState.IDLE) and quiet >= ENDED_AFTER_SECONDS:
        state = SessionState.ENDED
    agents = []
    for agent in view.subagents:
        silent = now - agent.last_event_at
        running = agent.running and silent < ENDED_AFTER_SECONDS
        stale = running and agent.current_action is not None and silent > STALE_AFTER_SECONDS
        action = None if stale or not running else agent.current_action
        agents.append(
            agent.model_copy(update={"running": running, "stale": stale, "current_action": action})
        )
    return view.model_copy(
        update={
            "state": state,
            "stale": state == SessionState.WORKING and quiet > STALE_AFTER_SECONDS,
            "subagents": agents,
        }
    )


def _attention(view: SessionView) -> tuple[int, float]:
    """Blocked first (longest wait first), then working, idle, stale, ended, each newest first."""
    if view.state == SessionState.BLOCKED:
        return (0, view.last_event_at)
    if view.stale:
        return (3, -view.last_event_at)
    ranks = {SessionState.WORKING: 1, SessionState.IDLE: 2}
    return (ranks.get(view.state, 4), -view.last_event_at)


def ordered(views: Iterable[SessionView], now: float) -> list[SessionView]:
    """The views as of `now`, in the order that draws attention."""
    return sorted((settled(view, now) for view in views), key=_attention)


def doing(view: SessionView) -> tuple[str, float | None]:
    """What the session is on, and when its last call began when that is what is shown.

    `waiting on you` when a question is open, else the open tool call, else the next unticked plan
    item, else the last call (with its start, so a row can say how long ago). Empty without a call.
    """
    action = view.current_action
    if view.state == SessionState.BLOCKED or (action and action.tool == "AskUserQuestion"):
        return ("waiting on you", None)
    if action is not None:
        return (f"{action.tool} {action.summary}".rstrip(), None)
    if view.plan is not None:
        return (view.plan, None)
    if view.last_call is None:
        return ("", None)
    call = view.last_call
    return (f"last call: {call.tool} {call.summary}".rstrip(), call.started_at)
