from typing import Any

import httpx

from repo_files import PROJECT_VERSION


async def _document(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get("/api/openapi.json")
    assert response.status_code == 200
    return response.json()


async def test_the_document_lists_the_platform_routes_with_their_schemas(
    offline_client: httpx.AsyncClient,
) -> None:
    document = await _document(offline_client)
    assert document["paths"].keys() >= {
        "/api/health",
        "/api/ready",
        "/api/about",
        "/api/factory/dashboard",
        "/api/factory/runs",
        "/api/factory/prs/expensive",
        "/api/factory/scorers",
        "/api/factory/improvements",
    }

    def schema_ref(path: str, status: str) -> str:
        content = document["paths"][path]["get"]["responses"][status]["content"]
        media = "application/json" if status.startswith("2") else "application/problem+json"
        return str(content[media]["schema"]["$ref"])

    assert schema_ref("/api/health", "200") == "#/components/schemas/Health"
    assert schema_ref("/api/ready", "200") == "#/components/schemas/Ready"
    assert schema_ref("/api/about", "200") == "#/components/schemas/About"
    assert schema_ref("/api/ready", "503") == "#/components/schemas/Problem"
    schemas = document["components"]["schemas"]
    assert schemas["About"]["required"] == ["name", "version"]
    assert schemas["Problem"]["required"] == ["type", "title", "status", "detail"]


async def test_the_document_title_is_the_service_name(offline_client: httpx.AsyncClient) -> None:
    info = (await _document(offline_client))["info"]
    assert (info["title"], info["version"]) == ("code-factory", PROJECT_VERSION)
