"""The `memory_extras` module as the platform sees it."""

from code_factory.git.service import GitService
from code_factory.memory.service import MemoryService
from code_factory.memory_extras import tables  # noqa: F401  # puts the table on Base.metadata
from code_factory.memory_extras.adapters import DefinedTests, OriginWeb, RepositoryFiles
from code_factory.memory_extras.cli import memory_command
from code_factory.memory_extras.service import MemoryExtrasService
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.tickets.service import TicketService


def _provide(services: Services, resources: Resources) -> None:
    git = services.get(GitService)
    tests = DefinedTests(git)
    memory = services.get(MemoryService)
    extras = MemoryExtrasService(
        resources.uow,
        memory,
        services.get(TicketService),
        services.get(RepositoryService),
        RepositoryFiles(git),
        tests,
        OriginWeb(git),
    )
    memory.add_preparation(extras.prepare_admission)
    services.add(MemoryExtrasService, extras)
    resources.on_stopping.append(tests.close)


module = Module(name="memory_extras", provide=_provide, commands=(memory_command,))
