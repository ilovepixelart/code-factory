import httpx

from repo_files import PROJECT_VERSION


async def test_about_names_the_service_and_its_version(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/api/about")
    assert (response.status_code, response.json()) == (
        200,
        {"name": "code-factory", "version": PROJECT_VERSION},
    )
