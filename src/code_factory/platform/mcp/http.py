"""Mounting the MCP server in an ASGI app, so the web layer never imports FastMCP itself."""

from collections.abc import Sequence

from fastmcp.server.http import StarletteWithLifespan
from fastmcp.utilities.lifespan import combine_lifespans

from code_factory.platform.config import Settings
from code_factory.platform.mcp.access import Access
from code_factory.platform.mcp.server import build_mcp
from code_factory.platform.module import Module
from code_factory.platform.services import Services


def build_mcp_app(
    services: Services, modules: Sequence[Module], settings: Settings, access: Access
) -> StarletteWithLifespan:
    """The server over streamable HTTP, answering at its own root (mount it at `/mcp`).

    Host and Origin are always validated (DNS rebinding): loopback names and the configured host
    pass, so a page on another origin cannot drive the server from the owner's browser. Callers
    present a bearer token that `access.verifier` knows; any other request is answered 401.
    """
    return build_mcp(services, modules, access=access).http_app(
        path="/", host_origin_protection=True, allowed_hosts=[settings.advertised_host]
    )


__all__ = ["build_mcp_app", "combine_lifespans"]
