"""The roster: how a change applies to an agent, their order, and who takes which ticket."""

import math
from datetime import datetime

from code_factory.agents.models.agents import KEPT, AgentChange, AgentDefinition
from code_factory.agents.models.constants import ROLES, RUNTIMES, TICKET_TYPES
from code_factory.agents.rules.commands import runtime_template
from code_factory.agents.rules.contexts import with_context
from code_factory.agents.rules.names import check_name
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError

NUL_RULE = "a value cannot hold a NUL character"
INT64_MAX = 2**63 - 1
LIMIT_RULE = "a limit is a whole number above 0"
LIMIT_CEILING_RULE = f"{LIMIT_RULE} and at most {INT64_MAX:,}"
PRICE_RULE = (
    "a price is input_price and output_price together, each dollars per million tokens, 0 or more"
)


def blank() -> AgentDefinition:
    """The agent an add starts from: a claude agent with nothing set."""
    return AgentDefinition(name="", runtime=RUNTIMES[0])


def _check_runtime(runtime: str) -> None:
    if runtime not in RUNTIMES:
        *others, last = RUNTIMES
        msg = f"unknown runtime {runtime}: {', '.join(others)} or {last}"
        raise BadRequestError(msg)


def _check_takes(agent: AgentDefinition) -> None:
    for column in agent.roles:
        if column not in ROLES:
            msg = f"unknown column {column}: an agent works {', '.join(ROLES)}"
            raise BadRequestError(msg)
    for kind in agent.types:
        if kind not in TICKET_TYPES:
            msg = f"unknown ticket type {kind}: an agent takes {', '.join(TICKET_TYPES)}"
            raise BadRequestError(msg)
    if any("\0" in label for label in agent.labels):
        raise BadRequestError(NUL_RULE)
    if any(not label.strip() or "," in label for label in agent.labels):
        msg = "a label is a word without a comma"
        raise BadRequestError(msg)


def _check_limits(agent: AgentDefinition) -> None:
    if "\0" in agent.model:
        raise BadRequestError(NUL_RULE)
    # The runtime takes the model as `--model <value>`: a leading dash would read as a flag.
    if agent.model.startswith("-") or any(char.isspace() for char in agent.model):
        msg = "a model is one word, not starting with -"
        raise BadRequestError(msg)
    if 0 in (agent.max_tokens, agent.max_seconds):
        raise BadRequestError(LIMIT_RULE)
    if any(
        limit is not None and limit > INT64_MAX for limit in (agent.max_tokens, agent.max_seconds)
    ):
        raise BadRequestError(LIMIT_CEILING_RULE)


def _check_dollars(agent: AgentDefinition) -> None:
    prices = [price for price in (agent.input_price, agent.output_price) if price is not None]
    if len(prices) == 1 or any(not math.isfinite(price) or price < 0 for price in prices):
        raise BadRequestError(PRICE_RULE)
    cap = agent.max_daily_usd
    if cap is not None and (not math.isfinite(cap) or cap <= 0):
        msg = "a daily cap is dollars above 0"
        raise BadRequestError(msg)


def _paused(agent: AgentDefinition, paused: bool | None, now: datetime) -> datetime | None:
    if paused is None:
        return agent.paused_at
    return (agent.paused_at or now) if paused else None


def _merged(agent: AgentDefinition, change: AgentChange, now: datetime) -> AgentDefinition:
    """`agent` with each field the change names: absent keeps, a limit set to null clears."""
    fields = change.model_dump(exclude={"context", "paused"}, exclude_none=True)
    for tri in ("max_tokens", "max_seconds", "input_price", "output_price", "max_daily_usd"):
        given = getattr(change, tri)
        if given is KEPT:
            fields.pop(tri, None)
        else:
            fields[tri] = given
    return agent.model_copy(update={**fields, "paused_at": _paused(agent, change.paused, now)})


def apply_change(agent: AgentDefinition, change: AgentChange, now: datetime) -> AgentDefinition:
    """`agent` with the change applied, columns and types in their canonical order, each once.

    The checks run in the order the owner's sentences were written: context, name, runtime,
    columns, types and labels, model, limits, dollars.
    """
    now = now.replace(microsecond=0)
    merged = _merged(agent, change, now)
    if change.context is not None:
        merged = with_context(merged, change.context, now)
    check_name(merged.name)
    _check_runtime(merged.runtime)
    _check_takes(merged)
    _check_limits(merged)
    _check_dollars(merged)
    return merged.model_copy(
        update={
            "roles": [role for role in ROLES if role in merged.roles],
            "types": [kind for kind in TICKET_TYPES if kind in merged.types],
        }
    )


def takes(agent: AgentDefinition, kind: str, labels_csv: str) -> bool:
    """Whether the agent takes a ticket of type `kind` carrying the comma separated labels.

    Each list that is set must match, the types by the ticket's type, the labels by at least one;
    an empty list limits nothing.
    """
    typed = not agent.types or kind in agent.types
    have = [label.strip() for label in labels_csv.split(",")]
    return typed and (not agent.labels or any(label in agent.labels for label in have))


def move(
    agents: list[AgentDefinition], name: str, column: str, *, up: bool
) -> list[AgentDefinition]:
    """The agents with `name` one place up or down among those working `column`.

    It goes just before the agent above it there, or just after the one below; every other agent
    keeps its place relative to the rest.
    """
    at = next((i for i, agent in enumerate(agents) if agent.name == name), None)
    if at is None:
        msg = "no such agent"
        raise NotFoundError(msg)
    if column not in agents[at].roles:
        msg = f"{name} does not work {column}"
        raise BadRequestError(msg)
    working = [i for i, agent in enumerate(agents) if column in agent.roles]
    place = working.index(at)
    neighbour = working[place - 1] if up and place > 0 else None
    if not up and place + 1 < len(working):
        neighbour = working[place + 1]
    if neighbour is None:
        msg = f"{name} is already {'first' if up else 'last'} in {column}"
        raise ConflictError(msg)
    moved = list(agents)
    mover = moved.pop(at)
    # Up, the neighbour sits before the mover so its index holds; down, removing the mover shifts
    # the neighbour one place left and the mover goes after it, at the neighbour's old index.
    moved.insert(neighbour, mover)
    return moved


def _joined(parts: list[str]) -> str:
    *first, last = parts
    return f"{', '.join(first)} and {last}" if first else last


def rename_refusal(name: str, new: str, held: list[str]) -> str | None:
    """Why `name` cannot be renamed `new` while the board keeps these by its name; None if free."""
    if not held:
        return None
    return f"{name} {_joined(held)}, so it cannot be renamed; add a new agent named {new} instead"


def setup_for(
    agent: AgentDefinition | None,
    stand_in: str,
    repository_template: str,
    repository_model: str,
) -> tuple[str, str]:
    """The command template and model a run as `agent` starts with.

    A stand-in command replaces every template; else the agent's runtime template, or the
    repository's for no agent; the agent's model when it names one, else the repository's.
    """
    if stand_in:
        template = stand_in
    elif agent is not None:
        template = runtime_template(agent.runtime)
    else:
        template = repository_template
    model = agent.model if agent is not None and agent.model else repository_model
    return template, model
