"""The `repositories` module as the platform sees it."""

from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.repositories import tables  # noqa: F401  # puts the table on Base.metadata
from code_factory.repositories.service import RepositoryService


def _provide(services: Services, resources: Resources) -> None:
    services.add(RepositoryService, RepositoryService(resources.uow))


module = Module(name="repositories", provide=_provide)
