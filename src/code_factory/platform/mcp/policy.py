"""Which tool a caller may use and what a run may touch. Pure: the transports and tools call it.

The table is the one place the surface's access rules are written; `tests/platform/
test_mcp_policy.py` holds the same matrix by hand. A refusal is a sentence `<code>: <fact>. <what
to do>.` that a model can act on; the scope check runs before any lookup, so a ticket that does
not exist and one that exists are refused alike.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from code_factory.platform.errors import BadRequestError, ForbiddenError
from code_factory.platform.identity import Actor, Role

# The stages whose runs work a ticket. A run in any other stage can only ask `whoami`.
RUN_STAGES = frozenset({"spec", "build", "review", "split"})
# The review roles and the second readers of a spec (`read`) and a plan (`critique`): they read the
# ticket and its checks and record findings as notes or questions, nothing more.
ROLE_STAGES = frozenset({"qa", "security", "tests", "read", "critique"})
_READING = RUN_STAGES | ROLE_STAGES


@dataclass(frozen=True)
class ToolRule:
    """Who may call a tool: owner, coordinator, and the run stages (`None`: every stage)."""

    owner: bool = False
    coordinator: bool = False
    run: frozenset[str] | None = frozenset()


_EVERYONE = ToolRule(owner=True, coordinator=True, run=RUN_STAGES)
_READ_BY_ALL = ToolRule(owner=True, coordinator=True, run=_READING)
_OWNER = ToolRule(owner=True)
_BOARD = ToolRule(owner=True, coordinator=True)
_RUNS_AND_OWNER = ToolRule(owner=True, run=RUN_STAGES)

# Order is the order `tools/list` answers in (deterministic, so clients and prompt caches can rely
# on it).
TOOLS: dict[str, ToolRule] = {
    "whoami": ToolRule(owner=True, coordinator=True, run=None),
    "get_ticket": _READ_BY_ALL,
    "list_tickets": _BOARD,
    "create_ticket": _EVERYONE,
    "update_ticket": _OWNER,
    "list_activity": _READ_BY_ALL,
    "post_note": _READ_BY_ALL,
    "get_qa_holdout": ToolRule(run=frozenset({"qa"})),
    "read_document": ToolRule(owner=True, run=_READING),
    "write_document": _RUNS_AND_OWNER,
    "submit_review": ToolRule(run=frozenset({"review"})),
    "dismiss_finding": ToolRule(owner=True, run=frozenset({"build"})),
    "ask_question": ToolRule(run=_READING),
    "list_questions": _READ_BY_ALL,
    "answer_question": _OWNER,
    "search_memory": _READ_BY_ALL,
    "propose_memory": _EVERYONE,
    "list_runs": _BOARD,
    "start_run": _OWNER,
    "stop_run": _OWNER,
    "start_worktree": _OWNER,
    "get_checks": _READ_BY_ALL,
    "run_checks": _OWNER,
}

_RUN_DOCUMENTS: dict[str, tuple[str, ...]] = {
    "spec": ("mock", "notes", "requirements", "spec", "uat"),
    "build": ("notes",),
    "review": ("notes",),
    "split": ("notes",),
}

# (limit per run for a run, for a split run, for a coordinator); the owner has none.
_QUOTAS: dict[str, tuple[int, int, int]] = {
    "follow_up_tickets": (3, 50, 10),
    "memory_proposals": (5, 5, 5),
}
QUOTA_KINDS = tuple(_QUOTAS)
_QUOTA_SENTENCE = {
    "follow_up_tickets": (
        "{limit} follow-up tickets already created by this run. Put the rest in notes."
    ),
    "memory_proposals": "{limit} memory proposals already made by this run. Put the rest in notes.",
}


def may_call(actor: Actor, tool: str) -> bool:
    """Whether `actor` may call `tool` at all; an unknown tool is called by no one."""
    rule = TOOLS.get(tool)
    if rule is None:
        return False
    match actor.role:
        case Role.OWNER:
            return rule.owner
        case Role.COORDINATOR:
            return rule.coordinator
        case Role.RUN:
            return rule.run is None or actor.stage in rule.run
    return False


def visible(actor: Actor, names: Iterable[str]) -> list[str]:
    """The tools of `names` the actor may call, in the order given."""
    return [name for name in names if may_call(actor, name)]


def who(actor: Actor) -> str:
    """How a refusal names the caller: `a build run`, `a coordinator`, `the owner`."""
    if actor.role is Role.RUN:
        return f"a {actor.stage} run"
    return "a coordinator" if actor.role is Role.COORDINATOR else "the owner"


def refuse_tool(actor: Actor, tool: str) -> ForbiddenError:
    """The refusal of a tool the actor may not call."""
    return ForbiddenError(
        f"forbidden: {tool} is not available to {who(actor)}. whoami says what is."
    )


def scope_ticket(actor: Actor, ticket_id: str | None) -> str:
    """The ticket a call is about: a run's own, or the one an owner or coordinator names."""
    if actor.role is Role.RUN:
        own = actor.ticket_id
        if ticket_id is None or ticket_id == own:
            assert own is not None  # noqa: S101  # a run token always carries its ticket
            return own
        raise ForbiddenError(
            f"out_of_scope: this run is scoped to {own}; {ticket_id} is not available to it. "
            "Use ask_question if you need something from another ticket."
        )
    if ticket_id is None:
        msg = f"ticket_id is required for {who(actor)}; pass the ticket's id, for example CF-12"
        raise BadRequestError(msg)
    return ticket_id


def scope_repository(actor: Actor, repository: str | None) -> str | None:
    """The repository a call is about: a run's or coordinator's own, or what the owner names."""
    if actor.role is Role.OWNER or repository is None or repository == actor.repository:
        return repository if actor.role is Role.OWNER else actor.repository
    raise ForbiddenError(
        f"out_of_scope: this token is scoped to repository {actor.repository}; "
        f"{repository} is not available to it."
    )


def writable_documents(actor: Actor) -> list[str] | None:
    """The documents `write_document` accepts from the actor, sorted; `None` for every document."""
    if actor.role is Role.OWNER:
        return None
    if actor.role is Role.RUN:
        return sorted(_RUN_DOCUMENTS.get(actor.stage or "", ()))
    return []


def _listing(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def check_document_write(actor: Actor, name: str) -> None:
    """Refuse a document the actor's stage may not write, saying which it may."""
    allowed = writable_documents(actor)
    if allowed is None or name in allowed:
        return
    writable = _listing(allowed) if allowed else "none"
    raise ForbiddenError(
        f"forbidden: {who(actor)} may not write {name}. Writable here: {writable}."
    )


def quota(actor: Actor, kind: str) -> int | None:
    """How many of `kind` the actor's run may make; `None` for the owner."""
    if actor.role is Role.OWNER:
        return None
    per_run, per_split, per_coordinator = _QUOTAS[kind]
    if actor.role is Role.COORDINATOR:
        return per_coordinator
    return per_split if actor.stage == "split" else per_run


def check_quota(actor: Actor, kind: str, *, used: int) -> None:
    """Refuse the next use when `used` has reached the quota."""
    limit = quota(actor, kind)
    if limit is not None and used >= limit:
        raise ForbiddenError("limit: " + _QUOTA_SENTENCE[kind].format(limit=limit))
