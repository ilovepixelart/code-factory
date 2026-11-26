import pytest

from code_factory.sessions.models import AgentView, Event, SessionState
from code_factory.sessions.rules import derive


def event(seq: int, name: str, agent: str | None = None, **payload: object) -> Event:
    return Event(seq, "s", agent, name, float(seq), "s.jsonl", seq, dict(payload))


@pytest.mark.parametrize(
    ("names", "state"),
    [
        (["UserPromptSubmit"], "working"),
        (["UserPromptSubmit", "Stop"], "idle"),
        (["Stop", "UserPromptSubmit"], "working"),
        (["PermissionRequest"], "blocked"),
        (["PermissionRequest", "PostToolUse"], "working"),
        (["PermissionRequest", "PostToolUseFailure"], "working"),
        (["PermissionRequest", "UserPromptSubmit"], "working"),
        (["PermissionRequest", "Stop"], "idle"),
        (["PermissionRequest", "Notification"], "blocked"),
        (["PermissionRequest", "SessionEnd"], "ended"),
        (["SessionEnd", "UserPromptSubmit"], "ended"),
        (["PermissionRequest", "PostToolUse", "PermissionRequest"], "blocked"),
    ],
)
def test_the_state_follows_the_latest_permission_stop_and_end(names: list[str], state: str) -> None:
    view = derive.derive_unsettled(
        [event(1, "SessionStart")] + [event(at + 2, name) for at, name in enumerate(names)]
    )
    assert view is not None
    assert view.state == SessionState(state)


def test_a_session_start_forgets_what_came_before_it() -> None:
    view = derive.derive_unsettled(
        [event(1, "SessionEnd"), event(2, "SessionStart"), event(3, "UserPromptSubmit")]
    )
    assert view is not None
    assert view.state == SessionState.WORKING


def agent_view(*names: str) -> AgentView:
    events = [event(at + 1, name, "a", agent_type="Plan") for at, name in enumerate(names)]
    view = derive.derive_unsettled(events)
    assert view is not None
    return view.subagents[0]


@pytest.mark.parametrize(
    ("names", "running"),
    [
        (["SubagentStart"], True),
        (["SubagentStart", "SubagentStop"], False),
        (["SubagentStart", "SubagentStop", "SubagentStart"], True),
        (["SubagentStop", "SubagentStart", "PreToolUse"], True),
        (["PreToolUse", "SubagentStop"], False),
    ],
)
def test_a_subagent_runs_from_its_latest_start_until_its_stop(
    names: list[str], running: bool
) -> None:
    assert agent_view(*names).running is running


def test_a_subagent_started_twice_began_at_its_latest_start() -> None:
    agent = agent_view("SubagentStart", "SubagentStop", "SubagentStart", "PreToolUse")
    assert (agent.started_at, agent.last_event_at, agent.agent_type) == (3.0, 4.0, "Plan")


def test_a_stopped_subagent_has_no_open_call() -> None:
    assert agent_view("SubagentStart", "PreToolUse", "SubagentStop").current_action is None
    assert agent_view("SubagentStart", "PreToolUse").current_action is not None
