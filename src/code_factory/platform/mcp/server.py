"""The `code-factory` MCP server: the tools every module registers."""

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastmcp import FastMCP

from code_factory import PACKAGE_NAME, __version__
from code_factory.platform.mcp.access import Access, Guard
from code_factory.platform.mcp.errors import DomainErrors
from code_factory.platform.mcp.verifier import ActorTokenVerifier
from code_factory.platform.mcp.whoami import register_whoami
from code_factory.platform.module import Module
from code_factory.platform.services import Services

type Lifespan = Callable[[FastMCP], AbstractAsyncContextManager[Any]]


def build_mcp(
    services: Services,
    modules: Sequence[Module],
    lifespan: Lifespan | None = None,
    *,
    access: Access,
) -> FastMCP:
    """Build the server over `services`, the same ones the API uses, with each module's tools.

    `lifespan` is the startup of a server that runs by itself (stdio). The server mounted in the
    HTTP app has none: the app's own lifespan starts the shared runtime. `access` says how callers
    are identified (see `Access`); every call passes the guard, which keeps a caller to the tools
    its role and stage allow.
    """
    mcp = FastMCP(
        PACKAGE_NAME,
        version=__version__,
        lifespan=lifespan,
        mask_error_details=True,
        auth=ActorTokenVerifier(access.verifier, access.roles) if access.bearer else None,
    )
    mcp.add_middleware(DomainErrors())
    mcp.add_middleware(Guard(access))
    register_whoami(mcp)
    for module in modules:
        if module.register_tools is not None:
            module.register_tools(mcp, services)
    return mcp
