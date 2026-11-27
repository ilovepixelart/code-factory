"""What the runs service reads and drives in other modules, as protocols over its own shapes.

`adapters/neighbours.py` implements each over the owning module's service. The service sees only
these, so a test supplies fakes and no module's tables.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from code_factory.runs.models import Repair, RunHooks


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class LogUsage(_Frozen):
    """What a run's log reports; `None` for what no record says, never 0."""

    cost: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None

    @property
    def tokens(self) -> int | None:
        """Input plus output tokens; `None` when neither was reported."""
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)


class Limit(_Frozen):
    """A run's end on its runtime's usage limit; `reset` is epoch seconds, `None` when unstated."""

    reset: float | None = None


class TicketFacts(_Frozen):
    """A ticket as a start reads it. `blockers` are the ids of its unmerged blockers."""

    id: str
    number: int
    repository: str
    title: str
    kind: str
    labels: tuple[str, ...] = ()
    branch: str = ""
    column: str = "build"
    source: str = ""
    budget: str = ""
    parallel: str = ""
    blockers: tuple[str, ...] = ()


class Tree(_Frozen):
    """A ticket's worktree or clone as a run is given it."""

    name: str
    path: Path
    branch: str
    made: bool = False  # the start made it, so a failed start removes it


class Claimed(_Frozen):
    """The agent a claim picked (empty: the default agent) and the ones it passed over."""

    agent: str = ""
    lease_id: int | None = None
    passed_over: tuple[str, ...] = ()


class Given(_Frozen):
    """What a run of an agent starts with; `fingerprint` changes when any of it does.

    `refusal` is the sentence of a failed model check, `max_seconds` the agent's own time limit.
    """

    agent: str
    runtime: str
    model: str
    connection: str
    fingerprint: str
    refusal: str | None = None
    max_seconds: int | None = None
    max_tokens: int | None = None
    input_price: float | None = None
    output_price: float | None = None
    local: bool = False


class Settings(_Frozen):
    """The repository's `config.toml` as a run reads it, with its defaults."""

    run_timeout_s: int = 3600
    limit_wait_s: int = 3600
    budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    review_other_model: bool = False
    escalate: bool = False
    preview_command: str | None = None
    preview_idle_s: int | None = None
    permission_reviewer: str | None = None
    permission_reviewer_limit: int = 20
    permission_approval: bool = True
    attempts: int | None = None


@dataclass(frozen=True)
class LaunchPlan:
    """Everything the command of one run is made of; the token is a secret and never shown."""

    run_id: str
    stage: str
    ticket: TicketFacts
    tree: Tree
    given: Given
    permissions: str
    remaining: float | None
    exit_file: Path
    log: Path
    prompt: str | None = None
    nudge: str | None = None
    looping: bool = False
    iteration: int = 1
    timeout_s: int = 3600
    lifetime_s: int = 3600
    token: str = field(default="", repr=False)


@dataclass(frozen=True)
class Launch:
    """The process of one run: the wrapper's command line and environment.

    `files` are what the run wrote outside its worktree and the end removes; `digest` names the
    task the run was given.
    """

    argv: tuple[str, ...]
    env: dict[str, str] = field(repr=False)
    digest: str = ""
    files: tuple[Path, ...] = ()


class Tickets(Protocol):
    """The tickets module."""

    async def facts(self, ticket_id: str) -> TicketFacts:
        """The ticket; `NotFoundError` for an unknown id."""
        ...

    async def record_event(
        self, ticket_id: str, kind: str, run_id: str, data: dict[str, object], at: datetime
    ) -> None:
        """Append `kind` to the ticket's history once for the run: a repeat adds nothing."""
        ...

    async def clear_branch(self, ticket_id: str) -> None:
        """Take the ticket's branch away."""
        ...


class Teams(Protocol):
    """The team module's claims."""

    async def claim_for_run(self, ticket_id: str, stage: str, settings: Settings) -> Claimed:
        """Claim the ticket and pick its agent; `ConflictError` with the sentence on refusal."""
        ...

    async def beat_start(self, ticket_id: str, lease_id: int) -> bool:
        """Keep this exact starting claim while work is being prepared."""
        ...

    async def attach_run(self, ticket_id: str, run_id: str, *, lease_id: int | None = None) -> None:
        """Record a run under the ticket's claim."""
        ...

    async def end_claim(
        self, ticket_id: str, run_id: str | None, *, lease_id: int | None = None
    ) -> None:
        """End the claim, with a run only one it is under; nothing when gone or taken again."""
        ...

    async def start_refusal(self, ticket_id: str, stage: str, settings: Settings) -> str | None:
        """The sentence a start would meet from claims and agents, or `None`."""
        ...


class Trees(Protocol):
    """The git module's trees."""

    async def start(self, repository: str, ticket_id: str, attempt: int) -> Tree:
        """The ticket's tree for an attempt, made when it is not there."""
        ...

    async def head(self, tree: Tree) -> str:
        """The commit checked out in the tree."""
        ...

    async def commits(self, repository: str, base: str, new: str) -> list[str]:
        """The commits `new` adds to `base`, oldest first."""
        ...

    async def tree_id(self, repository: str, commit: str) -> str:
        """The content hash of the fetched commit, or an empty string when unavailable."""
        ...

    async def uncommitted(self, repository: str, tree: Tree) -> bool:
        """Whether the tree holds changes that are not committed."""
        ...

    async def fetch_back(self, repository: str, tree: Tree) -> str:
        """Bring the tree's branch back to the main repository; why it was refused, else ''."""
        ...

    async def save(self, repository: str, ticket_id: str, tree: Tree) -> None:
        """Keep the tree's unfinished work in a ref."""
        ...

    async def remove(self, repository: str, tree: Tree) -> None:
        """Remove the tree."""
        ...

    async def redirection(self, repository: str, tree: Tree) -> str:
        """The git sentence when the tree's git folder is not the one the board made, else ''."""
        ...


class Agents(Protocol):
    """The agents module: what a run starts with, its command and its log's facts."""

    async def given(self, agent: str, stage: str) -> Given:
        """The agent's setup (the default agent for ''): its model check and fingerprint."""
        ...

    async def probe(self, given: Given) -> None:
        """Ask the model's server whether it answers; no lock is held while it does."""
        ...

    def launch_refusal(self, given: Given) -> str | None:
        """Why no run of the setup can launch now (the board is not served, say), or `None`."""
        ...

    async def launch(self, plan: LaunchPlan) -> Launch:
        """The wrapper's command and environment for the run; `UnavailableError` when it cannot."""
        ...

    async def log_usage(self, log: Path) -> LogUsage:
        """What the run's log reports; nothing for a link, a missing or an oversize log."""
        ...

    def usage_limit(self, log_text: str) -> Limit | None:
        """The usage limit a log ended on, `None` when it did not."""
        ...


class Tokens(Protocol):
    """The auth module's run tokens."""

    async def issue(
        self, run_id: str, ticket_id: str | None, stage: str, repository: str, lifetime_s: int
    ) -> str:
        """A token for one run; its value is shown once."""
        ...

    async def revoke(self, run_id: str) -> None:
        """End every token of the run."""
        ...


class Memory(Protocol):
    """The memory module's delivery."""

    async def deliver(self, run_id: str, ticket: TicketFacts, stage: str) -> str:
        """Record what the run is given of memory; the digest of it."""
        ...


class Config(Protocol):
    """The repositories' configuration."""

    async def settings(self, repository: str) -> Settings:
        """The repository's settings, the defaults when it has none."""
        ...

    async def root(self, repository: str) -> Path:
        """The repository's main checkout."""
        ...


class Flow(Protocol):
    """The steps a run's start and end set off in the modules that own them."""

    async def prepare_build(self, ticket_id: str) -> bool:
        """Seal the requested spec checks, returning true if this caller waited for proof."""
        ...

    async def verify_build(self, ticket_id: str, head: str) -> None:
        """Recheck the sealed files against the actual Build candidate under the claim."""
        ...

    async def admit_repair(self, ticket_id: str, repair: Repair, run_id: str = "") -> None:
        """Check admission, reserving the round when called with a run ID."""
        ...

    async def release_repair(self, ticket_id: str, run_id: str) -> None:
        """Release the reservation when the process could not start."""
        ...

    async def build_ended(self, ticket_id: str, head: str) -> None:
        """A build run left commits ending at `head` on the ticket's branch."""
        ...

    async def review_ended(self, ticket_id: str, run_id: str, head: str) -> None:
        """A review run of `head` ended: its verdict moves the ticket."""
        ...


@dataclass(frozen=True)
class RunPorts:
    """Every port the runs service uses."""

    tickets: Tickets
    teams: Teams
    trees: Trees
    agents: Agents
    tokens: Tokens
    memory: Memory
    config: Config
    flow: Flow


class PreviewSetup(Protocol):
    """What a live preview needs of the git and agents modules."""

    async def tree_of(self, repository: str, ticket_id: str) -> Path | None:
        """The ticket's worktree, `None` when it has none."""
        ...

    def unavailable_reason(self) -> str | None:
        """Why this board cannot start a preview, or None."""
        ...

    async def contain(self, argv: Sequence[str], tree: Path, port: int) -> Launch:
        """`argv` run inside the sandbox on `port`; `UnavailableError` when it cannot be."""
        ...


class HookCommandSource(Protocol):
    """The hooks module: how its hooks start."""

    def run_hooks(self) -> RunHooks:
        """The command of each hook a run's settings carry."""
        ...
