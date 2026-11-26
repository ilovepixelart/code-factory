"""What delivery reads and drives in other modules, as protocols over its own shapes."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from code_factory.delivery.models import Tracker
from code_factory.stages.models import Hold


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Candidate(_Frozen):
    """A ticket delivery may ship or merge."""

    id: str
    repository: str
    title: str
    branch: str
    column: str
    archived: bool = False
    source: str = ""


class Switches(_Frozen):
    """The repository's delivery settings."""

    ship: bool = False
    merge_waits: bool = True
    github_issues: bool = False
    github_label: str = ""
    github_label_required: bool = False
    trackers: tuple[Tracker, ...] = ()


class NewIssueTicket(_Frozen):
    """An issue to file as a ticket."""

    repository: str
    title: str
    description: str
    source: str
    type: str
    priority: str
    labels: list[str] = []
    due: str = ""
    parent: str = ""
    blocked_by: list[str] = []


class Tickets(Protocol):
    """The tickets module."""

    async def candidates(self) -> list[Candidate]:
        """Tickets in Build or Review with a branch."""
        ...

    async def get(self, ticket_id: str) -> Candidate:
        """One ticket; `NotFoundError` for an unknown id."""
        ...

    async def create(self, new: NewIssueTicket) -> str:
        """File the ticket; its id."""
        ...

    async def behaviour(self, ticket_id: str) -> str:
        """The ticket's `## Behaviour` notes and what its screen captures are; empty for neither."""
        ...

    async def record_pull(self, ticket_id: str, url: str, state: str) -> None:
        """Give the ticket its pull request at `url` in `state` (`open`, `merged`, `closed`)."""
        ...

    async def record_merged(self, ticket_id: str) -> None:
        """Record that the ticket's work is merged."""
        ...


class Git(Protocol):
    """The git module."""

    async def default_branch(self, repository: str) -> str:
        """The repository's default branch."""
        ...

    async def tip(self, repository: str, branch: str) -> tuple[str, str]:
        """(local tip, origin tip) of the branch, '' when absent."""
        ...

    async def holds_code(self, repository: str, base: str, tip: str) -> bool:
        """Whether the tip changes anything but docs."""
        ...

    async def push(self, repository: str, commit: str, branch: str) -> None:
        """Push the commit by id to the branch; held by the screen or refused raises."""
        ...

    async def messages(self, repository: str, base: str, tip: str) -> list[str]:
        """The messages of the commits the tip adds."""
        ...

    async def paths(self, repository: str, base: str, tip: str) -> list[str]:
        """The paths the tip changes."""
        ...

    async def descends(self, repository: str, older: str, newer: str) -> bool:
        """Whether `newer` holds `older`."""
        ...

    async def remote_url(self, repository: str) -> str | None:
        """Where origin points."""
        ...

    async def catch_up(self, repository: str) -> None:
        """Fetch origin, and move the main checkout forward when it is on the default branch."""
        ...


class Checks(Protocol):
    """The checks module."""

    async def verdict(self, repository: str, ticket_id: str, head: str) -> str:
        """`passed`, `failed` or `missing`."""
        ...

    async def configured(self, repository: str) -> bool:
        """Whether a checks command is set."""
        ...

    async def queue(self, ticket_id: str, head: str) -> None:
        """Queue the checks on a shipped head when they are due."""
        ...


class MergePolicy(Protocol):
    """The stage rules for an unattended merge."""

    async def automatic_hold(self, ticket_id: str, head: str) -> Hold | None:
        """Why the board must wait before merging the shipped head on its own."""
        ...


class Places(Protocol):
    """Tracked repositories and their settings."""

    async def names(self) -> list[str]:
        """Every tracked repository."""
        ...

    async def root(self, repository: str) -> Path:
        """The main checkout."""
        ...

    async def switches(self, repository: str) -> Switches:
        """The delivery settings."""
        ...


@dataclass(frozen=True)
class DeliveryPorts:
    """Every port delivery uses."""

    tickets: Tickets
    git: Git
    checks: Checks
    places: Places
    policy: MergePolicy
