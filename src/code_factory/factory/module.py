"""The `factory` module as the platform sees it."""

from collections.abc import Callable

from code_factory.factory.routes import router
from code_factory.factory.service import FactoryPorts, FactoryService
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services


def build_module(ports_of: Callable[[Services], FactoryPorts]) -> Module:
    """The module over the ports `code_factory.app` builds from the providers' services."""

    def provide(services: Services, _resources: Resources) -> None:
        services.add(FactoryService, FactoryService(ports_of(services)))

    return Module(name="factory", provide=provide, router=router)
