"""An agent's owner context and the versions it replaced."""

from datetime import datetime

from code_factory.agents.models.agents import AgentDefinition, ContextVersion, epoch
from code_factory.agents.models.constants import CONTEXT_LIMIT, CONTEXT_VERSIONS
from code_factory.platform.errors import BadRequestError, NotFoundError


def context_refusal(text: str) -> str | None:
    """Why `text` cannot be an agent's context: a NUL character, or more than 8,000 characters."""
    if "\0" in text:
        return "a value cannot hold a NUL character"
    if len(text) > CONTEXT_LIMIT:
        return (
            f"context is {len(text):,} characters; "
            f"an agent's context holds at most {CONTEXT_LIMIT:,}"
        )
    return None


def _replaced(agent: AgentDefinition, text: str | None, at: datetime | None) -> AgentDefinition:
    """`agent` with `text` current since `at`; the replaced context becomes the newest version."""
    history = list(agent.context_history)
    if agent.context is not None and agent.context_at is not None:
        history.insert(0, ContextVersion(at=agent.context_at, context=agent.context))
    history.sort(key=lambda version: version.at, reverse=True)
    return agent.model_copy(
        update={
            "context": text,
            "context_at": at,
            "context_history": history[:CONTEXT_VERSIONS],
        }
    )


def with_context(agent: AgentDefinition, text: str, now: datetime) -> AgentDefinition:
    """`agent` with the context `text` from `now`; blank clears, the same text changes nothing."""
    if (why := context_refusal(text)) is not None:
        raise BadRequestError(why)
    kept = text if text.strip() else None
    if kept == agent.context:
        return agent
    return _replaced(agent, kept, None if kept is None else now)


def restore(agent: AgentDefinition, at: int) -> AgentDefinition:
    """`agent` with its context version of `at` current again under its own time.

    The context it replaces is kept as a version.
    """
    for place, version in enumerate(agent.context_history):
        if epoch(version.at) == at:
            rest = [*agent.context_history[:place], *agent.context_history[place + 1 :]]
            return _replaced(
                agent.model_copy(update={"context_history": rest}), version.context, version.at
            )
    msg = f"{agent.name} has no context version of {at}"
    raise NotFoundError(msg)
