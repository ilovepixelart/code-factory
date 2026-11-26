"""The `health` module as the platform sees it."""

from code_factory.health.routes import router
from code_factory.health.service import ReadinessService
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services


def _provide(services: Services, resources: Resources) -> None:
    services.add(
        ReadinessService,
        ReadinessService(resources.engine, resources.settings.ready_timeout_s),
    )


module = Module(name="health", provide=_provide, router=router)
