"""The built web app served at `/`, from a folder the test writes."""

import re
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest

from code_factory.app import create_app
from code_factory.platform.config import Settings
from code_factory.platform.web.webapp import DEFAULT_APP_DIR
from repo_files import ROOT

INDEX = '<!doctype html><div id="app"></div>'
# `shasum -a 256` of each file below, listed by path in byte order, hashed once more.
BUILD_HASH = "5666511e5ee8c6be74d0f5bf71ab88d1aa8f1cb0cdfdb20de6d6003a1dc09f2a"
FILES = {
    "index.html": INDEX,
    "assets/app-1.js": "console.log(1)",
    "theme-early.js": "x",
    "favicon.svg": "<svg/>",
    "manifest.webmanifest": "{}",
    "icon-192.png": "png",
    "apple-touch-icon.png": "png",
}


def _write(folder: Path) -> Path:
    for name, text in FILES.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return folder


@pytest.fixture
async def served(tmp_path: Path, offline_settings: Settings) -> AsyncGenerator[httpx.AsyncClient]:
    app = create_app(offline_settings, app_dir=_write(tmp_path), guarded=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        yield client


async def test_the_page_is_served_at_the_root_and_revalidated_on_every_load(
    served: httpx.AsyncClient,
) -> None:
    response = await served.get("/")
    assert (response.status_code, response.text) == (200, INDEX)
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"
    assert (
        await served.get("/", headers={"if-none-match": response.headers["etag"]})
    ).status_code == 304


@pytest.mark.parametrize(
    "path", ["/tickets/sample/CF-1", "/memory", "/reply/" + "a" * 64, "/x/y/z"]
)
async def test_a_client_route_answers_with_the_page_so_a_reload_works(
    served: httpx.AsyncClient, path: str
) -> None:
    response = await served.get(path)
    assert (response.status_code, response.text) == (200, INDEX)


@pytest.mark.parametrize(
    ("path", "media_type", "cache_control"),
    [
        ("/assets/app-1.js", "text/javascript", "public, max-age=31536000, immutable"),
        ("/theme-early.js", "text/javascript", "no-cache"),
        ("/favicon.svg", "image/svg+xml", "no-cache"),
        ("/manifest.webmanifest", "application/manifest+json", "no-cache"),
        ("/icon-192.png", "image/png", "no-cache"),
        ("/apple-touch-icon.png", "image/png", "no-cache"),
    ],
)
async def test_a_file_is_served_with_its_media_type_and_cache_policy(
    served: httpx.AsyncClient, path: str, media_type: str, cache_control: str
) -> None:
    response = await served.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == media_type
    assert response.headers["cache-control"] == cache_control


async def test_a_missing_asset_is_a_404_not_the_page(served: httpx.AsyncClient) -> None:
    response = await served.get("/assets/app-0.js")
    assert (response.status_code, response.json()["detail"]) == (404, "not found")
    assert "cache-control" not in response.headers


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
async def test_an_unknown_api_path_answers_the_json_404(
    served: httpx.AsyncClient, method: str
) -> None:
    response = await served.request(method, "/api/nowhere/at/all")
    assert (response.status_code, response.json()["detail"]) == (404, "not found")


@pytest.mark.parametrize("path", ["/%2e%2e/%2e%2e/pyproject.toml", "/assets/%2e%2e/%2e%2e/x"])
async def test_a_path_out_of_the_folder_never_reads_a_file(
    served: httpx.AsyncClient, path: str
) -> None:
    response = await served.get(path)
    assert "[project]" not in response.text


@pytest.mark.parametrize("path", ["/", "/api/health", "/api/nowhere", "/favicon.svg"])
async def test_every_answer_names_the_build_and_carries_the_security_headers(
    served: httpx.AsyncClient, path: str
) -> None:
    response = await served.get(path)
    assert response.headers["x-code-factory-build"] == BUILD_HASH
    assert "script-src 'self'" in response.headers["content-security-policy"]


async def test_a_changed_file_changes_the_build_hash(
    tmp_path: Path, offline_settings: Settings
) -> None:
    _write(tmp_path)
    (tmp_path / "assets/app-1.js").write_text("console.log(2)")
    app = create_app(offline_settings, app_dir=tmp_path, guarded=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.get("/")
    assert response.headers["x-code-factory-build"] != BUILD_HASH


async def test_an_unbuilt_app_says_how_to_build_it_and_the_api_still_answers(
    tmp_path: Path, offline_settings: Settings
) -> None:
    app = create_app(offline_settings, app_dir=tmp_path / "missing", guarded=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        page = await client.get("/")
        api = await client.get("/api/about")
    assert page.status_code == 503
    assert (
        page.json()["detail"]
        == "the web app is not built; run `pnpm --dir web install && pnpm --dir web build`"
    )
    assert api.status_code == 200
    assert "x-code-factory-build" not in api.headers


def test_the_vite_build_lands_where_the_server_and_the_wheel_read_it() -> None:
    config = (ROOT / "web" / "vite.config.ts").read_text()
    out_dir = re.search(r"outDir: '([^']+)'", config)
    assert out_dir is not None
    assert (ROOT / "web" / out_dir.group(1)).resolve() == DEFAULT_APP_DIR


async def test_the_builds_own_favicon_is_served_and_revalidated(
    served: httpx.AsyncClient,
) -> None:
    first = await served.get("/favicon.svg")
    assert first.text == "<svg/>"
    again = await served.get("/favicon.svg", headers={"if-none-match": first.headers["etag"]})
    assert again.status_code == 304


async def test_without_a_build_the_docs_favicon_is_served_and_revalidated(
    tmp_path: Path, offline_settings: Settings
) -> None:
    app = create_app(offline_settings, app_dir=tmp_path / "missing", guarded=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        first = await client.get("/favicon.svg")
        again = await client.get("/favicon.svg", headers={"if-none-match": first.headers["etag"]})
    assert first.status_code == 200
    assert first.text.startswith("<svg ")
    assert again.status_code == 304
