"""Which subagents are at work on a ticket right now."""

from collections.abc import Iterable

from code_factory.sessions.models import AtWork, SessionState, SessionView


def subagents_at_work(views: Iterable[SessionView]) -> list[AtWork]:
    """The running subagents of the sessions that have not ended, oldest run first.

    Each is on the ticket whose worktree its newest tool call names; one that names none is left
    out. `kind` is `reviewer` when the agent type contains `review`.
    """
    found = []
    for view in views:
        if view.state == SessionState.ENDED:
            continue
        for agent in view.subagents:
            if not agent.running or agent.ticket is None:
                continue
            action = agent.current_action
            doing = "between tool calls" if action is None else f"{action.tool} {action.summary}"
            found.append(
                AtWork(
                    ticket=agent.ticket,
                    session_id=view.session_id,
                    agent_id=agent.agent_id,
                    name=f"{agent.agent_type} {agent.agent_id[:4]}",
                    kind="reviewer" if "review" in agent.agent_type else "session",
                    doing=doing.rstrip(),
                    since=agent.started_at,
                    last_event_at=agent.last_event_at,
                )
            )
    return sorted(found, key=lambda at_work: at_work.since)
