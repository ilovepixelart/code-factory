"""What the checks module reads from modules that import it, as protocols `app.py` binds."""

from typing import Protocol

from code_factory.checks.models import PullHead


class ForgePort(Protocol):
    """The commit statuses and open pull requests of the forge; the delivery module answers it."""

    async def post_commit_status(
        self, repository: str, commit: str, state: str, context: str, description: str
    ) -> bool:
        """Post the status; whether the forge took it."""
        ...

    async def open_pull_heads(self, repository: str) -> list[PullHead]:
        """The open pull requests' heads, one per ticket."""
        ...
