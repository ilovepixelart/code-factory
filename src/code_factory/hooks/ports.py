"""What the hooks service reads and drives in other modules, as protocols over its own shapes.

`service/neighbours.py` implements each over the owning module's service. The service sees only
these, so a test supplies fakes and no module's tables.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from code_factory.hooks.models import ReleaseFact, TellConfirm
from code_factory.tickets.models import Activity


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class TicketFacts(_Frozen):
    """A ticket as recall and the error report read it."""

    id: str
    repository: str
    title: str
    stage: str
    branch: str = ""
    labels: list[str] = []


class Checkout(_Frozen):
    """The repository a folder belongs to and the branch checked out in it."""

    repository: str
    branch: str


class NewsFact(_Frozen):
    """What was said on a ticket since a session last heard, and the marks that confirm it."""

    text: str
    confirm: TellConfirm


class MemoryContext(_Frozen):
    """What decides which memory entries a session is given."""

    stage: str = ""
    paths: list[str] = []
    labels: list[str] = []


class MemoryRecall(_Frozen):
    """What memory gives a session: the lines kept and cut as `(id, line)`, in load order."""

    kept: list[tuple[str, str]] = []
    left: list[tuple[str, str]] = []
    overflow: str | None = None
    index: list[str] = []


class NewBug(_Frozen):
    """A production bug a first error report files."""

    repository: str
    title: str
    description: str
    source: str
    caused_by: list[str]


class BoardAddress(_Frozen):
    """Where the serving board listens."""

    host: str
    port: int


class Talk(Protocol):
    """The talk module's news."""

    async def peek(self, ticket_id: str, session_id: str, since: datetime) -> NewsFact | None:
        """What the session has not been given; nothing is marked."""
        ...

    async def confirm(self, ticket_id: str, session_id: str, marks: TellConfirm) -> None:
        """Mark what a session was given."""
        ...


class Permissions(Protocol):
    """The runs module's permission requests."""

    async def request(
        self, run_id: str, payload: dict[str, Any], *, sandboxed: bool, wait: float
    ) -> dict[str, Any]:
        """The hook output for a tool call of a run; the owner is waited for at most `wait`."""
        ...

    async def record(
        self,
        run_id: str,
        tool: str,
        *,
        allow: bool,
        by: Literal["policy", "reviewer", "owner"],
        reason: str,
    ) -> None:
        """Record a decision made outside a request."""
        ...

    async def rules(self) -> list[str]:
        """The owner's standing rules."""
        ...

    def kind(self, tool: str, tool_input: object) -> str | None:
        """The standing rule that would allow the call, `None` for a compound command."""
        ...


class Runs(Protocol):
    """The runs module's start facts."""

    async def started(self, run_id: str) -> datetime | None:
        """When the run started, `None` for an unknown run."""
        ...


class Tickets(Protocol):
    """The tickets module."""

    async def get(self, ticket_id: str) -> TicketFacts:
        """The ticket; `NotFoundError` for an unknown id."""
        ...

    async def by_branch(self, repository: str, branch: str) -> TicketFacts | None:
        """The ticket of the repository that holds the branch."""
        ...

    async def requirements(self, ticket_id: str) -> list[str]:
        """The rows of the ticket's requirements table as `<id>: <requirement>`."""
        ...

    async def record(self, ticket_id: str, kind: str, data: dict[str, object], by: str) -> None:
        """Append a record to the ticket's history."""
        ...

    async def by_source(self, repository: str, source: str) -> TicketFacts | None:
        """The ticket of the repository filed from the source."""
        ...

    async def reports(self, ticket_id: str) -> int:
        """How many `reported` records the ticket's history holds."""
        ...

    async def create_bug(self, bug: NewBug) -> str:
        """File the bug; its id."""
        ...

    async def activity(self) -> list[tuple[str, Activity]]:
        """Every record of every tracked repository's tickets as `(repository, record)`."""
        ...


class Memory(Protocol):
    """The memory module's recall."""

    async def recall(
        self, repository: str, context: MemoryContext, *, ticket_id: str | None, run_id: str | None
    ) -> MemoryRecall:
        """What a session is given; for a run it records the delivery."""
        ...


class Checkouts(Protocol):
    """What git says about a folder."""

    async def of(self, cwd: str) -> Checkout | None:
        """The tracked repository and branch of the folder, `None` outside one."""
        ...

    async def changed(self, repository: str, branch: str) -> list[str]:
        """The paths the branch changes against the default branch; empty when unknown."""
        ...


class Auth(Protocol):
    """The auth module's sign-in."""

    async def mint(self) -> str:
        """A one-time sign-in value."""
        ...

    async def spend(self, nonce: str) -> None:
        """Use a value up without signing anyone in."""
        ...

    async def end_sessions(self) -> int:
        """End every owner session; how many."""
        ...


class Releases(Protocol):
    """The releases and settings a report is tied to."""

    async def published(self, repository: str) -> list[ReleaseFact]:
        """The published releases, oldest first."""
        ...

    async def watch_days(self, repository: str) -> int | None:
        """The repository's `[release] watch_days`, `None` when unset."""
        ...


class Repositories(Protocol):
    """The tracked repositories."""

    async def exists(self, name: str) -> bool:
        """Whether the repository is tracked."""
        ...


class Opener(Protocol):
    """Opens a URL in the default browser."""

    async def open_url(self, url: str) -> None:
        """`OpenerUnavailableError` or `OSError` when it cannot."""
        ...


class Probe(Protocol):
    """Asks whether a board answers."""

    async def up(self, base: str) -> bool:
        """Whether a board answers at `base`."""
        ...


@dataclass(frozen=True)
class HookPorts:
    """Every port the hooks service uses."""

    talk: Talk
    permissions: Permissions
    runs: Runs
    tickets: Tickets
    memory: Memory
    checkouts: Checkouts
    auth: Auth
    releases: Releases
    repositories: Repositories
    opener: Opener
    probe: Probe
    board: BoardAddress
