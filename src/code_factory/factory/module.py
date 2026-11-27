"""The `factory` module as the platform sees it."""

from collections.abc import Callable
from dataclasses import replace

from code_factory.factory import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.factory.routes import router
from code_factory.factory.service import FactoryPorts, FactoryService, OwnerTimeService
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services


def build_module(ports_of: Callable[[Services], FactoryPorts]) -> Module:
    """The module over the ports `code_factory.app` builds from the providers' services."""

    def provide(services: Services, resources: Resources) -> None:
        ports = replace(ports_of(services), owner_time=OwnerTimeService(resources.uow))
        services.add(FactoryService, FactoryService(ports))

    return Module(name="factory", provide=provide, router=router)
