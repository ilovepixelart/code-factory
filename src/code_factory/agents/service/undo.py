"""The stored inverse of a write: build one, and apply it when its target is as it was left."""

from typing import Any

from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.models.answers import UndoStep
from code_factory.agents.models.connections import ConnectionDefinition
from code_factory.platform.errors import ConflictError

AGENT_ADD = "agent.add"
AGENT_REMOVE = "agent.remove"
AGENT_REPLACE = "agent.replace"
AGENT_ORDER = "agent.order"
CONNECTION_ADD = "connection.add"
CONNECTION_REMOVE = "connection.remove"
CONNECTION_REPLACE = "connection.replace"


def dump(item: AgentDefinition | ConnectionDefinition | None) -> dict[str, Any] | None:
    """A definition as the JSON an undo step keeps."""
    return None if item is None else item.model_dump(mode="json")


def step(kind: str, **payload: object) -> UndoStep:
    """An undo step of `kind` holding `payload`."""
    return UndoStep(kind=kind, payload=dict(payload))


def changed_since(name: str) -> ConflictError:
    """The refusal of an undo whose target was changed after the write."""
    return ConflictError(f"{name} changed since; nothing was undone")
