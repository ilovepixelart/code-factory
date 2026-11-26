"""Pure ASGI layers (no `BaseHTTPMiddleware`: it breaks context variables for the layers below).

Outermost first: `RequestId`, `SecurityHeaders`, `HostGuard`, `ErrorBoundary`.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from code_factory.platform.identity import redact
from code_factory.platform.logging import request_id_var
from code_factory.platform.web.errors import error_response, internal_error_response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "x-request-id"
# A caller's id is echoed into logs and headers: only a short, plain token is accepted.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

# `script-src 'self'`: no inline or evaluated script anywhere; Swagger UI is served with
# same-origin files only (see `platform/web/docs.py`). Styles may be inline: shadcn-vue's chart
# (Unovis) sets its colours as style attributes and <style> elements, refused under `'self'`.
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "content-security-policy": CSP,
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


def _request_id(scope: Scope) -> str:
    for name, value in scope["headers"]:
        if name == REQUEST_ID_HEADER.encode():
            candidate = str(value.decode("latin-1"))
            if _VALID_REQUEST_ID.fullmatch(candidate):
                return candidate
    return uuid.uuid4().hex


class RequestId:
    """Gives every request an id: in a context variable, a response header and an access record."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Set the id for the duration of the request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _request_id(scope)
        token = request_id_var.set(request_id)
        status = 0
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": redact(scope["path"]),
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            request_id_var.reset(token)


class SecurityHeaders:
    """Adds the security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Wrap `send` so the headers land on `http.response.start`."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]"})
INVALID_HOST_SENTENCE = "invalid host header"


def _host_allowed(host_header: str, port: int) -> bool:
    name, separator, given_port = host_header.lower().rpartition(":")
    if not separator or name.endswith(":") or "]" in given_port:
        name, given_port = host_header.lower(), ""  # no port: `localhost` or `[::1]`
    return name in LOOPBACK_HOSTS and given_port in {"", str(port)}


# The one host name the board's links use, where its session cookie lives.
CANONICAL_HOST = "127.0.0.1"


class HostGuard:
    """Refuses a request whose `Host` is not a loopback name on the configured port.

    DNS rebinding: a page on another origin resolves its own domain to 127.0.0.1 and calls the
    server from the owner's browser, with that domain in `Host`.
    """

    def __init__(self, app: ASGIApp, *, port: int) -> None:
        self.app = app
        self.port = port

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass a loopback `Host` on; answer a 400 problem to any other.

        A page asked on another loopback name (`localhost`, `[::1]`) moves to 127.0.0.1, the name
        every link the board prints uses: the session cookie belongs to one host name, so a sign-in
        on 127.0.0.1 is missing on `localhost`. The API, `/mcp` and changes are answered in place.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        host = Headers(scope=scope).get("host", "")
        if not _host_allowed(host, self.port):
            await error_response(400, INVALID_HOST_SENTENCE)(scope, receive, send)
            return
        if _moves(scope, host):
            query = scope.get("query_string", b"").decode("latin-1")
            target = f"http://{CANONICAL_HOST}:{self.port}{scope['path']}" + (
                f"?{query}" if query else ""
            )
            await RedirectResponse(target, status_code=308)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _moves(scope: Scope, host: str) -> bool:
    """Whether a request is a page asked on a loopback name other than 127.0.0.1."""
    path = scope["path"]
    return (
        scope["method"] in {"GET", "HEAD"}
        and not host.lower().startswith(f"{CANONICAL_HOST}:")
        and host.lower() != CANONICAL_HOST
        and path not in {"/api", "/mcp"}
        and not path.startswith(("/api/", "/mcp/"))
    )


class ErrorBoundary:
    """The catch-all: logs an unexpected exception with the request id and answers 500.

    Starlette runs its own handler for `Exception` outside every user layer, so its answer would
    carry neither the request id nor the security headers; this layer sits inside them instead.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the app; answer 500 if it raises before the response has started."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            logger.exception("unhandled error")
            if started:
                raise
            response = internal_error_response()
            await response(scope, receive, send)
