"""Queries over the tickets module's tables. Every method runs in the session it is given."""

from code_factory.tickets.repository.documents import DocumentRepository, MockFileRepository
from code_factory.tickets.repository.tickets import Links, TicketRepository

__all__ = ["DocumentRepository", "Links", "MockFileRepository", "TicketRepository"]
