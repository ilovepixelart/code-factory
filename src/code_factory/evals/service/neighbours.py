"""The evals ports over the owning modules' services, resolved from the registry per call."""

from pathlib import Path

from code_factory.evals.models import Filed, Scorer
from code_factory.evals.rules import scorers_of
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.settings.models import ConfigUnjudgedError
from code_factory.settings.service import SettingsService
from code_factory.tickets.service import TicketService


class PlacesAdapter:
    """Repositories and their `[[scorers]]`."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def names(self) -> list[str]:
        """Every tracked repository."""
        return [r.name for r in await self._services.get(RepositoryService).list()]

    async def scorers(self, repository: str) -> list[Scorer]:
        """The scorers of `config.toml`; none while the config cannot be judged."""
        root = await self._services.get(RepositoryService).get(repository)
        try:
            config = await self._services.get(SettingsService).load(Path(root))
        except ConfigUnjudgedError:
            return []
        return scorers_of(entry.model_dump() for entry in config.scorers or [])


class TicketsAdapter:
    """Tickets a scorer filed."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def filed(self, repository: str) -> list[Filed]:
        """The repository's tickets whose source starts `scorer:`."""
        found = await self._services.get(TicketService).list()
        return [
            Filed(source=t.source, open=not (t.merged or t.archived), id=t.id)
            for t in found
            if t.repository == repository and t.source.startswith("scorer:")
        ]
