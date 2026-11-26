"""Who may call `/api`: the owner's session cookie, and changes made from the board's own pages.

Pure ASGI layers, like the rest of `middleware.py`. The page, its files, the sign-in link and
`/mcp` (bearer tokens) are outside this guard; `/api/health` and `/api/ready` answer without it
as probes.
"""

import re
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from code_factory.platform.web.errors import error_response

OWNER_COOKIE = "code_factory_owner"
API_PREFIX = "/api/"
OPEN_PATHS = frozenset({"/api/health", "/api/ready"})
# A pushed reply link: read and pressed without the sign-in, its token the only credential. The
# origin and JSON rules still hold for the press.
REPLY_LINK = re.compile(r"/api/reply/[0-9a-f]{64}")
REPLY_METHODS = frozenset({"GET", "POST"})
# An agent's hooks: each route takes a run's or the owner's bearer token itself (hooks/routes.py).
HOOK_PREFIX = "/api/hooks/"
# Changes to these are made only from the board's own pages, so a request with no `Origin`
# header (a script on the machine) is refused even with the cookie.
ORIGIN_REQUIRED = ("/api/agent-definitions", "/api/agent-context", "/api/connections")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SIGN_IN_HINT = "run uv run code-factory open"
READ_REFUSAL = f"reading the board needs the owner's sign-in: {SIGN_IN_HINT}"
WRITE_REFUSAL = f"a change needs the owner's sign-in: {SIGN_IN_HINT}"
FOREIGN_ORIGIN = "changes are made from the board's own pages"
ORIGIN_MISSING = "agents and connections are changed from the board's own pages"
NOT_JSON = "changes are sent as JSON"

type SessionCheck = Callable[[str], Awaitable[bool]]


def _guarded(scope: Scope) -> bool:
    if scope["type"] != "http":
        return False
    path = str(scope["path"])
    return path.startswith(API_PREFIX) and path not in OPEN_PATHS


def _reply_link(scope: Scope) -> bool:
    return scope["method"] in REPLY_METHODS and REPLY_LINK.fullmatch(str(scope["path"])) is not None


def _cookies(headers: Headers) -> list[str]:
    values = []
    for line in headers.getlist("cookie"):
        for pair in line.split(";"):
            name, _, value = pair.strip().partition("=")
            if name == OWNER_COOKIE and value:
                values.append(value)
    return values


class WriteOrigin:
    """Refuses a change from another origin, a body that is not JSON, or a missing `Origin`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass reads and same-origin JSON changes on; answer the refusal otherwise."""
        if not _guarded(scope) or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        refusal = self._refusal(scope, Headers(scope=scope))
        if refusal is None:
            await self.app(scope, receive, send)
            return
        await error_response(*refusal)(scope, receive, send)

    @staticmethod
    def _refusal(scope: Scope, headers: Headers) -> tuple[int, str] | None:
        origin = headers.get("origin")
        site = headers.get("sec-fetch-site")
        foreign_origin = origin is not None and urlsplit(origin).netloc != headers.get("host")
        if foreign_origin or site not in {None, "same-origin", "none"}:
            return 403, FOREIGN_ORIGIN
        if origin is None and scope["path"].startswith(ORIGIN_REQUIRED):
            return 403, ORIGIN_MISSING
        kind = headers.get("content-type")
        if kind is not None and kind.split(";")[0].strip().lower() != "application/json":
            return 415, NOT_JSON
        return None


class OwnerGuard:
    """Serves `/api` only with a session cookie that `check` accepts."""

    def __init__(self, app: ASGIApp, *, check: SessionCheck) -> None:
        self.app = app
        self.check = check

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass a signed-in request on; answer 403 to any other."""
        if (
            not _guarded(scope)
            or scope["method"] == "OPTIONS"
            or _reply_link(scope)
            or str(scope["path"]).startswith(HOOK_PREFIX)
        ):
            await self.app(scope, receive, send)
            return
        for cookie in _cookies(Headers(scope=scope)):
            if await self.check(cookie):
                await self.app(scope, receive, send)
                return
        reason = READ_REFUSAL if scope["method"] in SAFE_METHODS else WRITE_REFUSAL
        await error_response(403, reason)(scope, receive, send)
