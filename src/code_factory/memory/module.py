"""The `memory` module as the platform sees it."""

from code_factory.memory import tables  # noqa: F401  # puts the table on Base.metadata
from code_factory.memory.routes import router
from code_factory.memory.service import MemoryService
from code_factory.memory.tools import register_tools
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services


def _provide(services: Services, resources: Resources) -> None:
    services.add(MemoryService, MemoryService(resources.uow))


module = Module(name="memory", provide=_provide, router=router, register_tools=register_tools)
