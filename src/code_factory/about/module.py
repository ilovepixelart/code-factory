"""The `about` module as the platform sees it."""

from code_factory.about.routes import router
from code_factory.about.service import AboutService
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services


def _provide(services: Services, _resources: Resources) -> None:
    services.add(AboutService, AboutService())


module = Module(name="about", provide=_provide, router=router)
