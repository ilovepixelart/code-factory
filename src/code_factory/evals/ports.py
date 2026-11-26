"""What evals reads of other modules, as protocols over its own shapes."""

from typing import Protocol

from code_factory.evals.models import Filed, Scorer


class Places(Protocol):
    """Tracked repositories and their scorers."""

    async def names(self) -> list[str]:
        """Every tracked repository."""
        ...

    async def scorers(self, repository: str) -> list[Scorer]:
        """The repository's `[[scorers]]`, in file order."""
        ...


class Tickets(Protocol):
    """The tickets a scorer filed."""

    async def filed(self, repository: str) -> list[Filed]:
        """Tickets of the repository whose source starts `scorer:`."""
        ...
