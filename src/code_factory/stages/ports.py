"""What the stages module reads from modules that import it, as protocols they bind."""

from collections.abc import Mapping
from typing import Protocol

from code_factory.stages.models import BranchFacts


class LogReader(Protocol):
    """Reads the text of a checks log from what a `checks` record names.

    The checks module binds it (`StageService.bind_log_reader`): it alone knows where logs live and
    which names are safe to open, so this module never opens a path a ledger record gives.
    """

    async def read(self, log: str) -> str | None:
        """The log's text, or `None` when it is missing, outside the logs' folder or unreadable."""
        ...


class FactsSource(Protocol):
    """Reads the branch facts of a repository's tickets; the git module's service answers it."""

    async def read(self, repository: str, tickets: Mapping[str, str]) -> dict[str, BranchFacts]:
        """The facts of each ticket (id to its branch); a ticket git could not read is unknown."""
        ...
