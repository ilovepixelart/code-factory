import pytest

from code_factory.sessions.models import AtWork, SessionState, SessionView
from code_factory.sessions.rules import derive
from code_factory.sessions.rules.at_work import subagents_at_work
from code_factory.sessions.rules.page import session_json
from code_factory.sessions.rules.settle import doing, ordered, settled
from sessions_values import NOW, answer, events_by_session, sample_events

ROWS = answer("/api/sessions")["body"]


def view_of(session_id: str) -> SessionView:
    """The unsettled view of a sample session, in the folder the golden row names."""
    row = next(row for row in ROWS if row["session_id"] == session_id)
    view = derive.derive_unsettled(events_by_session(sample_events())[session_id])
    assert view is not None
    return view.model_copy(update={"repository": row["repository"], "branch": row["branch"]})


@pytest.mark.parametrize("row", ROWS, ids=[row["session_id"] or "none" for row in ROWS])
def test_a_session_of_the_sample_has_the_row_the_previous_answer_gave(
    row: dict[str, object],
) -> None:
    assert session_json(settled(view_of(str(row["session_id"])), NOW), NOW) == row


def test_the_sample_sessions_are_ordered_for_attention_as_the_previous_list_was() -> None:
    views = [view_of(str(row["session_id"])) for row in ROWS]
    assert [view.session_id for view in ordered(reversed(views), NOW)] == [
        row["session_id"] for row in ROWS
    ]


def test_no_events_have_no_view() -> None:
    assert derive.derive_unsettled([]) is None


def test_the_window_is_the_events_after_the_latest_session_start() -> None:
    events = events_by_session(sample_events())["s-idle"]
    # The sample's s-idle never restarts; a restart makes the earlier stop and call forgotten.
    restart = events[0].__class__(
        99, "s-idle", None, "SessionStart", 1790000200.0, "s-idle.jsonl", 99, {"cwd": "/new"}
    )
    view = derive.derive_unsettled([*events, restart])
    assert view is not None
    assert (view.state, view.last_prompt, view.last_call, view.cwd) == (
        SessionState.WORKING,
        "",
        None,
        "/new",
    )
    assert view.transcript.endswith("/transcripts/s-idle.jsonl")


@pytest.mark.parametrize(
    ("quiet", "stale", "state"),
    [
        (600.0, False, "working"),
        (600.5, True, "working"),
        (3599.0, True, "working"),
        (3600.0, False, "ended"),
    ],
)
def test_a_working_session_is_stale_after_600_seconds_and_ended_at_3600(
    quiet: float, stale: bool, state: str
) -> None:
    view = view_of("s-work")
    later = settled(view, view.last_event_at + quiet)
    assert (later.state.value, later.stale) == (state, stale)


def test_a_blocked_session_is_still_blocked_two_hours_later() -> None:
    view = view_of("s-block")
    assert settled(view, view.last_event_at + 7200).state == SessionState.BLOCKED


def test_an_idle_session_ends_at_3600_seconds_and_is_never_stale() -> None:
    view = view_of("s-idle")
    assert settled(view, view.last_event_at + 3599).state == SessionState.IDLE
    ended = settled(view, view.last_event_at + 3600)
    assert (ended.state, ended.stale) == (SessionState.ENDED, False)


def test_a_running_subagent_stops_running_after_3600_seconds_of_silence() -> None:
    view = view_of("s-sub")
    running = next(agent for agent in view.subagents if agent.agent_id == "a2")
    just = settled(view, running.last_event_at + 3599).subagents
    gone = settled(view, running.last_event_at + 3600).subagents
    assert next(a for a in just if a.agent_id == "a2").running
    stopped = next(a for a in gone if a.agent_id == "a2")
    assert (stopped.running, stopped.current_action) == (False, None)


def test_a_running_subagent_with_an_open_call_is_stale_after_600_seconds() -> None:
    view = view_of("s-sub")
    a2 = next(agent for agent in view.subagents if agent.agent_id == "a2")
    fresh = next(a for a in settled(view, a2.last_event_at + 600).subagents if a.agent_id == "a2")
    stale = next(a for a in settled(view, a2.last_event_at + 601).subagents if a.agent_id == "a2")
    assert (fresh.stale, fresh.current_action is not None) == (False, True)
    assert (stale.stale, stale.current_action) == (True, None)


@pytest.mark.parametrize(
    ("session_id", "line", "since"),
    [
        ("s-block", "waiting on you", None),
        ("s-work", "Read /x/app.py", None),
        ("s-idle", "last call: Bash ls", 1790000131.0),
        ("s-rest", "", None),
    ],
)
def test_the_row_line_says_what_the_session_is_on(
    session_id: str, line: str, since: float | None
) -> None:
    assert doing(settled(view_of(session_id), NOW)) == (line, since)


def test_an_open_question_reads_as_waiting_even_when_not_blocked() -> None:
    events = events_by_session(sample_events())["s-work"]
    question = events[0].__class__(
        99,
        "s-work",
        None,
        "PreToolUse",
        1790000980.0,
        "s-work.jsonl",
        99,
        {"tool_name": "AskUserQuestion", "tool_use_id": "q"},
    )
    view = derive.derive_unsettled([*events, question])
    assert view is not None
    assert doing(view) == ("waiting on you", None)


def test_the_plan_names_the_next_unticked_item() -> None:
    events = events_by_session(sample_events())["s-work"]
    todos = [
        {"content": "one", "status": "completed"},
        {"content": "two", "status": "in_progress"},
        {"content": "three", "status": "pending"},
    ]
    plan = events[0].__class__(
        99,
        "s-work",
        None,
        "PreToolUse",
        1790000960.0,
        "s-work.jsonl",
        99,
        {"tool_name": "TodoWrite", "tool_use_id": "p", "tool_input": {"todos": todos}},
    )
    view = derive.derive_unsettled([*events[:4], plan, *events[4:]])
    assert view is not None
    assert view.plan == "plan 2/3: two"
    closed = derive.derive_unsettled([*events[:4], plan])
    assert closed is not None
    assert doing(closed.model_copy(update={"current_action": None})) == ("plan 2/3: two", None)


def test_a_trimmed_plan_item_shows_its_head_with_an_ellipsis() -> None:
    events = events_by_session(sample_events())["s-work"]
    todos = [{"content": {"_trimmed_chars": 3000, "head": "start"}, "status": "pending"}]
    plan = events[0].__class__(
        99,
        "s-work",
        None,
        "PreToolUse",
        1790000960.0,
        "s-work.jsonl",
        99,
        {"tool_name": "TodoWrite", "tool_use_id": "p", "tool_input": {"todos": todos}},
    )
    view = derive.derive_unsettled([*events, plan])
    assert view is not None
    assert view.plan == "plan 1/1: start…"


@pytest.mark.parametrize(
    ("calls", "ticket"),
    [
        (["cd /r/.code-factory/worktrees/CF-12 && ls"], "CF-12"),
        (
            ["ls", "cat /r/.code-factory/worktrees/CF-9/a.py", "/r/.code-factory/worktrees/CF-1/"],
            "CF-9",
        ),
        (["cd /r/.code-factory/worktrees/ && ls", "/r/.code-factory/worktrees/CF-3"], "CF-3"),
        (["/r/.code-factory/worktrees/é"], None),
        (["no worktree here"], None),
    ],
)
def test_a_subagents_ticket_is_the_worktree_its_newest_call_names(
    calls: list[str], ticket: str | None
) -> None:
    assert derive.subagent_ticket(calls) == ticket


def test_a_subagent_that_names_a_worktree_is_at_work_on_its_ticket() -> None:
    events = events_by_session(sample_events())["s-sub"]
    tree = "/r/.code-factory/worktrees/CF-7/a.py"
    reviewer = events[0].__class__(
        99,
        "s-sub",
        "a2",
        "PreToolUse",
        1790000990.0,
        "s-sub.jsonl",
        99,
        {"tool_name": "Read", "tool_use_id": "r", "tool_input": {"file_path": tree}},
    )
    typed = events[0].__class__(
        98,
        "s-sub",
        "a3",
        "SubagentStart",
        1790000950.0,
        "s-sub.jsonl",
        98,
        {"agent_type": "code-reviewer"},
    )
    view = derive.derive_unsettled([*events, typed, reviewer])
    assert view is not None
    assert subagents_at_work([view]) == [
        AtWork(
            ticket="CF-7",
            session_id="s-sub",
            agent_id="a2",
            name="Plan a2",
            kind="session",
            doing="Read " + tree,
            since=1790000940.0,
            last_event_at=1790000990.0,
        )
    ]
    assert subagents_at_work([view.model_copy(update={"state": SessionState.ENDED})]) == []
