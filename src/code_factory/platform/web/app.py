"""The application factory: it serves whatever modules it is given and knows none of them."""

from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from fastapi import FastAPI

from code_factory import PACKAGE_NAME, __version__
from code_factory.platform.logging import install_record_factory
from code_factory.platform.mcp.access import Access
from code_factory.platform.mcp.http import build_mcp_app, combine_lifespans
from code_factory.platform.module import Module, Resources
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.platform.web import docs, webapp
from code_factory.platform.web.errors import install_error_handlers
from code_factory.platform.web.guard import OwnerGuard, SessionCheck, WriteOrigin
from code_factory.platform.web.lifespan import StartupLines, app_lifespan
from code_factory.platform.web.middleware import (
    ErrorBoundary,
    HostGuard,
    RequestId,
    SecurityHeaders,
)

MCP_PATH = "/mcp"


@dataclass(frozen=True)
class WebOptions:
    """What differs between the served app and a test's: all optional.

    `app_dir` holds the built Vue app (without a build the API still answers); `session_check`
    turns the sign-in guard on; `startup_lines` are printed after `serving on`.
    """

    app_dir: Path = webapp.DEFAULT_APP_DIR
    session_check: SessionCheck | None = None
    startup_lines: StartupLines | None = None


def create_web_app(
    resources: Resources,
    *,
    services: Services,
    modules: Sequence[Module],
    mcp_access: Access,
    options: WebOptions = WebOptions(),  # frozen, so one shared instance is safe
) -> FastAPI:
    """Build the app: module routers, layers, error handlers, the MCP server and the web app."""
    session_check, startup_lines = options.session_check, options.startup_lines
    built = webapp.load(options.app_dir)
    install_record_factory()
    mcp_app = build_mcp_app(services, modules, resources.settings, mcp_access)
    app = FastAPI(
        title=PACKAGE_NAME,
        version=__version__,
        lifespan=combine_lifespans(
            partial(
                app_lifespan,
                resources=resources,
                services=services,
                modules=modules,
                startup_lines=startup_lines,
            ),
            mcp_app.lifespan,
        ),
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = resources.settings
    app.state.services = services
    app.state.resources = resources
    if session_check is not None:
        app.add_middleware(OwnerGuard, check=session_check)
        app.add_middleware(WriteOrigin)
    # Last added is outermost: the request id wraps the headers, which wrap the error boundary.
    app.add_middleware(ErrorBoundary)
    # The port that was bound; a process that serves nothing answers on the configured one.
    app.add_middleware(HostGuard, port=services.get(Served).port or resources.settings.port)
    app.add_middleware(SecurityHeaders)
    app.add_middleware(RequestId)
    if built is not None:
        app.add_middleware(webapp.BuildHeader, build=built.build)
    install_error_handlers(app)
    app.include_router(docs.router)
    for module in modules:
        if module.router is not None:
            app.include_router(module.router)
    app.mount(docs.ASSETS_PATH, docs.assets(), name="docs-assets")
    app.mount(MCP_PATH, mcp_app)
    app.router.default = webapp.fallback(built)
    return app
