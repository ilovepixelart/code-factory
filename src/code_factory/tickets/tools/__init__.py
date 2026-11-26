"""The tickets module's MCP tools: tickets, their history, documents and reviews."""

from fastmcp import FastMCP

from code_factory.platform.services import Services
from code_factory.tickets.tools import activity, documents, review, tickets


def register_tools(mcp: FastMCP, services: Services) -> None:
    """Add the module's tools to `mcp`, in the order `tools/list` answers them."""
    tickets.register(mcp, services)
    activity.register(mcp, services)
    documents.register(mcp, services)
    review.register(mcp, services)
