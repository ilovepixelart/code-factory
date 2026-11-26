"""Swagger UI served by the app itself, under the strict Content-Security-Policy.

FastAPI's own docs page loads Swagger UI from a CDN and starts it with an inline script, both of
which the policy forbids. This page is a static file that loads same-origin JS and CSS and one
small same-origin script that starts the UI. The Swagger UI files are vendored in
`static/docs-assets/swagger-ui` (version pinned by a test).
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSETS_PATH = "/api/docs-assets"

router = APIRouter(include_in_schema=False)


@router.get("/api/docs")
async def docs() -> FileResponse:
    """The Swagger UI page."""
    return FileResponse(STATIC_DIR / "docs.html", media_type="text/html")


def assets() -> StaticFiles:
    """The same-origin files the page loads."""
    return StaticFiles(directory=STATIC_DIR / "docs-assets")
