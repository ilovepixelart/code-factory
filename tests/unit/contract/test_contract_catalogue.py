"""The route catalogue against the web app's source and against the served OpenAPI document."""

import json
import re

import httpx
import pytest

from code_factory.app import create_app
from code_factory.platform.config import Settings
from contract_catalogue import NOT_CALLED, PENDING_OWNERS, ROUTES, TICKETS_GOLDEN
from contract_catalogue import _ticket_page as ticket_page_shape
from contract_shapes import conforms
from repo_files import ROOT

_LITERAL = re.compile(r"""['"`](/api/[^'"`\s]*)['"`]""")
_SUFFIX = re.compile(r"`\$\{[\w.]+\}(/[\w/-]+)`")
_INTERPOLATION = re.compile(r"\$\{[^}]*\}")


def _web_sources() -> list[str]:
    folder = ROOT / "web" / "src"
    files = [*folder.rglob("*.ts"), *folder.rglob("*.vue")]
    return [f.read_text() for f in files if ".test." not in f.name and "test" not in f.parts]


def _segments(path: str) -> list[str]:
    return [("{}" if part.startswith("{") else part) for part in path.split("/")]


def _matches(called: str, route: str) -> bool:
    a, b = _segments(called), _segments(route)
    return len(a) == len(b) and all(x == y or "{}" in (x, y) for x, y in zip(a, b, strict=True))


def _unnamed(path: str) -> str:
    """A path with every parameter name dropped: the names are the app's, not FastAPI's."""
    return _INTERPOLATION.sub("{}", re.sub(r"\{[^}]*\}", "${}", path))


def _calls() -> set[str]:
    found: set[str] = set()
    for text in _web_sources():
        found.update(_INTERPOLATION.sub("{}", m).split("?")[0] for m in _LITERAL.findall(text))
    return found


def test_every_path_the_web_app_names_is_in_the_catalogue() -> None:
    catalogued = [route.path for route in ROUTES]
    assert len(_calls()) > 30
    missing = sorted(c for c in _calls() if not any(_matches(c, r) for r in catalogued))
    assert missing == []


def test_every_path_the_web_app_builds_from_a_base_ends_in_a_catalogued_action() -> None:
    suffixes = {s for text in _web_sources() for s in _SUFFIX.findall(text)}
    missing = sorted(s for s in suffixes if not any(r.path.endswith(s) for r in ROUTES))
    assert suffixes
    assert missing == []


def test_the_catalogue_names_each_method_and_path_once() -> None:
    pairs = [(route.method, route.path) for route in ROUTES]
    assert sorted(set(pairs)) == sorted(pairs)


def test_every_shape_loads_from_its_golden_or_spec() -> None:
    assert [route.path for route in ROUTES if route.shape and not route.shape()] == []


@pytest.fixture
async def served() -> set[tuple[str, str]]:
    settings = Settings(
        database_url="postgresql+asyncpg://nobody:not-a-password@127.0.0.1:1/never_connected",
        _env_file=None,
    )
    app = create_app(settings, guarded=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        document = (await client.get("/api/openapi.json")).json()
    return {
        (method.upper(), _unnamed(path))
        for path, operations in document["paths"].items()
        for method in operations
    }


def test_a_route_is_served_exactly_when_its_module_has_landed(served: set[tuple[str, str]]) -> None:
    wrong = [
        f"{route.method} {route.path}"
        for route in ROUTES
        if ((route.method, _unnamed(route.path)) in served) == (route.owner in PENDING_OWNERS)
    ]
    assert wrong == []


def test_no_served_route_is_missing_from_the_catalogue(served: set[tuple[str, str]]) -> None:
    catalogued = {(route.method, _unnamed(route.path)) for route in ROUTES} | NOT_CALLED
    assert sorted(served - catalogued) == []


def test_the_ticket_page_shape_accepts_every_golden_page_it_was_made_from() -> None:
    pages = [entry["view"] for entry in json.loads(TICKETS_GOLDEN.read_text())]
    shape = ticket_page_shape()
    assert [problem for page in pages for problem in conforms(page, shape)] == []


def test_the_ticket_page_shape_takes_ticket_ids_as_dynamic_keys() -> None:
    page = json.loads(TICKETS_GOLDEN.read_text())[0]["view"]
    page["titles"] = {"CF-999": "a ticket no golden has"}
    page["stages_by_id"] = {"CF-999": "build"}
    assert conforms(page, ticket_page_shape()) == []
