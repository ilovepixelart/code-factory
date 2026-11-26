"""The built web app (the Vue app's Vite output) served by the API process.

The build lands in `DEFAULT_APP_DIR`, which is package data, so a wheel carries it; the dev flow
runs Vite's server, which proxies `/api` here (`web/vite.config.ts`). The files are read once,
at construction, and answered from memory.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from code_factory.platform.web.docs import STATIC_DIR
from code_factory.platform.web.errors import error_response

DEFAULT_APP_DIR = Path(__file__).resolve().parent / "dist"
BUILD_HEADER = "x-code-factory-build"
NOT_BUILT = "the web app is not built; run `pnpm --dir web install && pnpm --dir web build`"
INDEX = "index.html"
FAVICON = "favicon.svg"
API_PREFIX = "api/"
ASSETS_PREFIX = "assets/"
IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"
_MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
    ".json": "application/json",
    ".woff2": "font/woff2",
    ".map": "application/json",
    ".txt": "text/plain; charset=utf-8",
}
_DEFAULT_MEDIA_TYPE = "application/octet-stream"


@dataclass(frozen=True)
class AppFile:
    """One file of the build, ready to answer with."""

    body: bytes
    media_type: str
    etag: str


@dataclass(frozen=True)
class BuiltApp:
    """Every file of the build by its path below the folder, and the hash of the whole."""

    files: dict[str, AppFile]
    build: str


def _hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(folder: Path) -> BuiltApp | None:
    """Read the build in `folder`; None when it holds no `index.html`.

    The build hash is the SHA-256 of the lines `shasum -a 256` prints for each file, listed by
    path in byte order, so a shell can reproduce it.
    """
    names = sorted(
        (path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()),
        key=str.encode,
    )
    if INDEX not in names:
        return None
    files: dict[str, AppFile] = {}
    listing = ""
    for name in names:
        body = (folder / name).read_bytes()
        digest = _hex(body)
        listing += f"{digest}  {name}\n"
        media_type = _MEDIA_TYPES.get(Path(name).suffix, _DEFAULT_MEDIA_TYPE)
        files[name] = AppFile(body, media_type, f'"{digest[:16]}"')
    return BuiltApp(files, _hex(listing.encode()))


def _cache_control(name: str) -> str:
    return IMMUTABLE if name.startswith(ASSETS_PREFIX) else REVALIDATE


def _matches(header: str | None, etag: str) -> bool:
    if header is None:
        return False
    return any(part.strip().removeprefix("W/") in {etag, "*"} for part in header.split(","))


def _answer(request: Request, name: str, file: AppFile) -> Response:
    headers = {"etag": file.etag, "cache-control": _cache_control(name)}
    if _matches(request.headers.get("if-none-match"), file.etag):
        return Response(status_code=304, headers=headers)
    return Response(file.body, media_type=file.media_type, headers=headers)


def _vendored_favicon() -> AppFile:
    body = (STATIC_DIR / FAVICON).read_bytes()
    return AppFile(body, _MEDIA_TYPES[".svg"], f'"{_hex(body)[:16]}"')


def _respond(request: Request, built: BuiltApp | None, favicon: AppFile) -> Response:
    path = request.url.path.removeprefix("/")
    if path.startswith(API_PREFIX) or request.method not in {"GET", "HEAD"}:
        return error_response(404, "not found")
    if built is None:
        # The API docs page names an icon: it has one without a build, too.
        return (
            _answer(request, path, favicon) if path == FAVICON else error_response(503, NOT_BUILT)
        )
    if path in built.files:
        return _answer(request, path, built.files[path])
    if path.startswith(ASSETS_PREFIX):
        return error_response(404, "not found")
    return _answer(request, INDEX, built.files[INDEX])


def fallback(built: BuiltApp | None) -> ASGIApp:
    """The ASGI app for a request no route answers: the app's files, else the page, else a 404.

    It is the router's `default`, so it runs only when no route matches, whatever is added to the
    app after it. A path under `/api/` or a method other than GET and HEAD is the JSON 404, never
    the page. An unknown `/assets/` name is a 404 too: a stale page asking for a retired chunk
    cannot run the page it would be given instead.
    """
    favicon = _vendored_favicon()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        await _respond(request, built, favicon)(scope, receive, send)

    return app


class BuildHeader:
    """Names the build on every answer, which is how an open tab learns the board was rebuilt."""

    def __init__(self, app: ASGIApp, build: str) -> None:
        self.app = app
        self.build = build

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Wrap `send` so the header lands on `http.response.start`."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_build(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[BUILD_HEADER] = self.build
            await send(message)

        await self.app(scope, receive, send_with_build)
