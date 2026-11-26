"""The FastMCP server assembly. Tools are registered by the modules, not defined here."""

from code_factory.platform.mcp.access import Access, current_actor
from code_factory.platform.mcp.server import build_mcp

__all__ = ["Access", "build_mcp", "current_actor"]
