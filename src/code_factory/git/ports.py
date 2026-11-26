"""What the git module reads from other modules, as protocols.

Each is one small adapter in `code_factory.app` over the owning module's service, so git never
imports tickets, github, checks or runs (tickets read git facts). A provider that is not built yet
is a null adapter that answers the sentence saying so.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from code_factory.git.models import HookOutcome, PullRef, TicketRef


@runtime_checkable
class RepositoryDirectory(Protocol):
    """The tracked repositories."""

    async def root_of(self, repository: str) -> Path:
        """The main checkout; raises `NotFoundError` for an unknown repository."""
        ...

    async def by_path(self, path: Path) -> str:
        """The tracked repository whose checkout holds `path`; raises `NotFoundError`."""
        ...


@runtime_checkable
class TicketPort(Protocol):
    """The ticket facts git needs."""

    async def ticket(self, repository: str, ticket_id: str) -> TicketRef:
        """The ticket; raises `NotFoundError`."""
        ...

    async def record_branch(self, repository: str, ticket_id: str, branch: str) -> None:
        """Record the branch on the ticket."""
        ...

    async def stack_parent(self, repository: str, ticket_id: str) -> str | None:
        """The branch of the ticket this one builds on, when it stacks on one."""
        ...


@runtime_checkable
class ForgePort(Protocol):
    """Pull requests."""

    async def open_pull(
        self, repository: str, *, branch: str, head: str, base: str, title: str
    ) -> PullRef:
        """Open (or find) the pull request of `branch`."""
        ...

    async def pull_state(self, ref: PullRef) -> str:
        """The forge's merge state words."""
        ...

    def is_clean(self, state: str) -> bool:
        """Whether `state` means the pull request can merge."""
        ...

    async def merge(self, ref: PullRef, head: str) -> None:
        """Merge the pull request at `head`."""
        ...


@runtime_checkable
class ChecksPort(Protocol):
    """The board's checks."""

    async def verdict(self, repository: str, ticket_id: str, head: str) -> str:
        """`passed`, `failed` or `missing`."""
        ...

    async def configured(self, repository: str) -> bool:
        """Whether the repository has a checks command."""
        ...


@runtime_checkable
class ScreenPort(Protocol):
    """The secret screen of what a push sends."""

    async def held(self, repository: str, branch: str, base: str, new: str) -> str | None:
        """Why the push is held, or `None`."""
        ...


@runtime_checkable
class HooksPort(Protocol):
    """The setup command of a repository."""

    async def setup_command(self, repository: str) -> str | None:
        """The configured setup command, if any."""
        ...

    async def run_setup(self, repository: str, ticket_id: str, tree: Path) -> HookOutcome:
        """Run it in `tree`."""
        ...
