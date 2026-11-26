"""Fixtures of the timeline tests: both sources on the isolated connection, one frozen moment."""

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.talk.service import TalkService
from code_factory.tickets.service import ActivityService
from code_factory.timeline.service import TimelineService
from talk_values import Clock
from ticket_values import NOW


@pytest.fixture
def talk_clock() -> Clock:
    """The talk's clock, at the moment the ticket is created (`ticket_values.NOW`)."""
    clock = Clock()
    clock.now = NOW
    return clock


@pytest.fixture
def talk(uow: UnitOfWork, talk_clock: Clock) -> TalkService:
    return TalkService(uow, clock=talk_clock)


@pytest.fixture
def timeline(activity: ActivityService, talk: TalkService) -> TimelineService:
    return TimelineService(activity, talk)
