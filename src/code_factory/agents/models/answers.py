"""What the agents service answers."""

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from pydantic import BaseModel, SecretStr

from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.models.checks import ModelCheck
from code_factory.agents.models.connections import (
    ConnectionDefinition,
    ConnectionKind,
    Found,
    Status,
)


class UndoStep(BaseModel):
    """The stored inverse of a write: a kind and a JSON payload, applied by `AgentService.undo`.

    The payload holds what the target was before and after the write, so the inverse is refused
    when the target has changed since.
    """

    kind: str
    payload: dict[str, Any]


class Changed(BaseModel):
    """A write's notice for the toast and the step that takes it back, `None` when none can."""

    notice: str
    undo: UndoStep | None = None


class AgentList(BaseModel):
    """The agents page: the roster, the runtimes with their gaps and each agent's last check."""

    agents: list[AgentDefinition]
    runtimes: tuple[str, ...]
    gaps: dict[str, list[dict[str, str]]]
    roles: tuple[str, ...]
    checks: dict[str, ModelCheck]
    problem: str = ""

    def wire(self) -> dict[str, Any]:
        """The answer the Vue app reads, keys in the order it was written."""
        return {
            "agents": [agent.wire() for agent in self.agents],
            "runtimes": list(self.runtimes),
            "gaps": self.gaps,
            "roles": list(self.roles),
            "checks": {name: check.wire() for name, check in self.checks.items()},
            "problem": self.problem,
        }


class ConnectionView(BaseModel):
    """A connection with whether its key is set (never the key) and whether it runs here."""

    connection: ConnectionDefinition
    key_set: bool
    here: bool

    def wire(self) -> dict[str, Any]:
        """The answer the Vue app reads."""
        wire = self.connection.wire()
        base = {key: wire[key] for key in ("name", "kind", "base_url", "key_env")}
        base["key_set"] = self.key_set
        base["here"] = self.here
        if "management_key_env" in wire:
            base["management_key_env"] = wire["management_key_env"]
        return base


class ConnectionList(BaseModel):
    """The connections page."""

    connections: list[ConnectionView]
    kinds: tuple[ConnectionKind, ...]
    problem: str = ""

    model_config = {"arbitrary_types_allowed": True}

    def wire(self) -> dict[str, Any]:
        """The answer the Vue app reads."""
        return {
            "connections": [view.wire() for view in self.connections],
            "kinds": [kind.wire() for kind in self.kinds],
            "problem": self.problem,
        }


class ConnectionStatus(BaseModel):
    """Which connections answer, the local servers found and each agent's reach."""

    connections: list[Status]
    local: list[Found]
    reach: dict[str, str]

    def wire(self) -> dict[str, Any]:
        """The answer the Vue app reads."""
        return {
            "connections": [status.model_dump() for status in self.connections],
            "local": [found.model_dump() for found in self.local],
            "reach": self.reach,
        }


class RunConnection(BaseModel):
    """What a run of an agent with a connection is started with; the values are secrets.

    `env` sets each variable, or removes it when `None`; `config_env` is the codex config text
    (empty for claude); `selector` is the model as the runtime names it.
    """

    env: dict[str, SecretStr | None]
    config_env: str = ""
    selector: str = ""


class Setup(BaseModel):
    """What a run starts with.

    The agent's name (empty for the default agent), the command template, the model and the
    agent's connection name (empty: none).
    """

    agent: str
    template: str
    model: str
    connection: str


class ResolvedAgent(BaseModel):
    """The agent a run starts as: its definition, its connection and what it starts with."""

    definition: AgentDefinition | None
    connection: ConnectionDefinition | None
    setup: Setup


class AgentFacts(BaseModel, frozen=True):
    """An agent as the team module reads it: same field names as its `TeamAgent`.

    `paused_at` is epoch seconds; `refusal` is the sentence of a failed model check, empty while
    the model is usable.
    """

    name: str
    roles: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    max_tokens: int | None = None
    max_seconds: int | None = None
    input_price: float | None = None
    output_price: float | None = None
    max_daily_usd: float | None = None
    paused_at: float | None = None
    runtime: str = ""
    connection: str = ""
    model: str = ""
    refusal: str = ""


class RenameGuard(Protocol):
    """What a module that keeps things by an agent's name says before the name changes."""

    async def holds(self, name: str, /) -> list[str]:
        """What it keeps by `name`, as `holds a claim on CF-3` or `has 2 runs`; none when free."""
        ...

    def frozen(self, name: str, /) -> AbstractAsyncContextManager[None]:
        """While open, nothing new is kept by `name`: a claim in flight finishes before it opens.

        The guard takes the lock its own writers take, so its `holds` answer stays true until
        the rename commits; it is held across that commit and released when the context closes.
        """
        ...
