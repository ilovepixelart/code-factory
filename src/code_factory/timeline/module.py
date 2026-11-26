"""The `timeline` module as the platform sees it."""

from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.talk.service import TalkService
from code_factory.tickets.service import ActivityService
from code_factory.timeline.service import TimelineService


def _provide(services: Services, resources: Resources) -> None:  # noqa: ARG001
    services.add(
        TimelineService, TimelineService(services.get(ActivityService), services.get(TalkService))
    )


module = Module(name="timeline", provide=_provide)
