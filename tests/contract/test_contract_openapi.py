"""The OpenAPI document is the contract: every request body names its fields."""

from typing import Any

import pytest

from code_factory.app import MCP_TOKEN_VARIABLE, create_app
from code_factory.platform.config import Settings


@pytest.fixture
def document(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv(MCP_TOKEN_VARIABLE, "cfo_" + "A" * 43)
    settings = Settings(database_url="postgresql+asyncpg://u:p@h:1/x_test", _env_file=None)
    return create_app(settings, guarded=False).openapi()


def _schema(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """The body's model; an optional body is `anyOf` the model and null."""
    given = [part for part in schema.get("anyOf", []) if part.get("type") != "null"]
    if len(given) == 1:
        schema = given[0]
    ref = schema.get("$ref", "")
    return document["components"]["schemas"][ref.rsplit("/", 1)[-1]] if ref else schema


# Claude Code's hook payload, passed whole: its keys change between runtime versions, and a key the
# board does not know must not cost the run its permission request.
OPEN_BODIES = frozenset({"POST /api/hooks/permission"})


def test_every_request_body_names_its_fields_and_refuses_others(
    document: dict[str, Any],
) -> None:
    loose = [
        f"{method.upper()} {path}"
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        for content in operation.get("requestBody", {}).get("content", {}).values()
        if not (schema := _schema(document, content["schema"])).get("properties")
        or schema.get("additionalProperties") is not False
    ]
    assert [name for name in loose if name not in OPEN_BODIES] == []


def test_the_archive_names_its_query(document: dict[str, Any]) -> None:
    parameters = document["paths"]["/api/archive"]["get"]["parameters"]
    assert [p["name"] for p in parameters] == ["q", "sort", "dir", "show", "page", "size"]
