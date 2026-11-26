from html.parser import HTMLParser
from typing import override

import httpx

# Swagger UI release the vendored files come from (https://www.npmjs.com/package/swagger-ui-dist).


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []
        self.scripts = 0
        self.stylesheets = 0
        self.inline_script_bodies: list[str] = []
        self.style_attributes: list[str] = []
        self.style_tags = 0
        self._in_script = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if "style" in values:
            self.style_attributes.append(tag)
        if tag == "style":
            self.style_tags += 1
        if tag == "script":
            self.scripts += 1
            self._in_script = True
            if values.get("src") is not None:
                self.urls.append(values["src"] or "")
        if tag == "link" and values.get("href") is not None:
            self.urls.append(values["href"] or "")
            self.stylesheets += values.get("rel") == "stylesheet"

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    @override
    def handle_data(self, data: str) -> None:
        if self._in_script and data.strip():
            self.inline_script_bodies.append(data)


async def test_the_docs_page_is_served_under_the_csp_with_nothing_inline(
    offline_client: httpx.AsyncClient,
) -> None:
    response = await offline_client.get("/api/docs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    directives = dict(
        part.strip().split(" ", 1)
        for part in response.headers["content-security-policy"].split(";")
    )
    assert directives["script-src"] == "'self'"
    page = _Page()
    page.feed(response.text)
    assert page.scripts >= 2
    assert page.stylesheets >= 1
    assert page.inline_script_bodies == []
    assert page.style_attributes == []
    assert page.style_tags == 0


async def test_every_asset_the_page_references_is_same_origin_and_answers_200(
    offline_client: httpx.AsyncClient,
) -> None:
    page = _Page()
    page.feed((await offline_client.get("/api/docs")).text)
    assert page.urls
    for url in page.urls:
        assert url.startswith("/"), f"{url} is not a same-origin path"
        assert not url.startswith("//"), f"{url} is protocol-relative"
        asset = await offline_client.get(url)
        assert asset.status_code == 200, url
        assert len(asset.content) > 100, url


async def test_the_docs_page_links_the_app_favicon_and_it_is_served_as_svg(
    offline_client: httpx.AsyncClient,
) -> None:
    page = _Page()
    page.feed((await offline_client.get("/api/docs")).text)
    assert "/favicon.svg" in page.urls
    favicon = await offline_client.get("/favicon.svg")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert favicon.text.startswith("<svg ")


async def test_the_initialiser_loads_the_openapi_document_that_exists(
    offline_client: httpx.AsyncClient,
) -> None:
    initialiser = (await offline_client.get("/api/docs-assets/docs-init.js")).text
    assert '"/api/openapi.json"' in initialiser
    document = await offline_client.get("/api/openapi.json")
    assert document.status_code == 200
    assert document.json()["openapi"].startswith("3.")


async def test_a_missing_asset_is_a_json_404(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/api/docs-assets/swagger-ui/missing.js")
    assert (response.status_code, response.json()["detail"]) == (404, "not found")
