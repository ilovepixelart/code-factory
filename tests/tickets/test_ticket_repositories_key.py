from fastapi import FastAPI

from code_factory.platform.mcp.scope import TicketRepositories
from code_factory.tickets.service import TicketService


def test_the_app_offers_the_ticket_service_as_the_scope_check_needs_it(
    offline_app: FastAPI,
) -> None:
    services = offline_app.state.services
    assert services.get(TicketRepositories) is services.get(TicketService)
