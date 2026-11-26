"""The `inbox` module as the platform sees it."""

from code_factory.inbox.routes import router
from code_factory.inbox.service import InboxService
from code_factory.inbox.service.neighbours import InboxSources
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services


def _provide(services: Services, resources: Resources) -> None:  # noqa: ARG001
    services.add(InboxService, InboxService(InboxSources(services)))


module = Module(name="inbox", provide=_provide, router=router)
