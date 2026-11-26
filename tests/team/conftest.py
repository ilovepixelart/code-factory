"""Fixtures of the team tests: the service over fake ports, on the isolated test database."""

from collections.abc import Awaitable, Callable

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.team.service import TeamService
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import TicketService
from team_fakes import FakeClock, Fakes
from ticket_values import OWNER


@pytest.fixture
def fakes() -> Fakes:
    """The fake ports; a test sets what each answers."""
    return Fakes()


@pytest.fixture
def clock() -> FakeClock:
    """The service's clock, at `team_values.NOW` until a test moves it."""
    return FakeClock()


@pytest.fixture
def team(uow: UnitOfWork, fakes: Fakes, clock: FakeClock) -> TeamService:
    """The team service over the fake ports and the isolated connection, no git."""
    return TeamService(uow, fakes.ports, clock=clock)


@pytest.fixture
def more_tickets(tickets: TicketService) -> Callable[[int], Awaitable[list[Ticket]]]:
    """A factory of `n` fresh tickets in the `sample` repository."""

    async def make(count: int) -> list[Ticket]:
        return [
            await tickets.create(NewTicket(repository="sample", title=f"Ticket {n}"), by=OWNER)
            for n in range(count)
        ]

    return make
