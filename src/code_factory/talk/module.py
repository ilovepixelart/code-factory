"""The `talk` module as the platform sees it."""

from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.talk import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.talk.service import TalkService
from code_factory.talk.tools import register_tools


def _provide(services: Services, resources: Resources) -> None:
    services.add(TalkService, TalkService(resources.uow))


module = Module(name="talk", provide=_provide, register_tools=register_tools)
