"""A database that cannot be reached is a 503 with a sentence, not an internal error."""

import httpx


async def test_a_route_over_an_unreachable_database_answers_503(
    offline_client: httpx.AsyncClient,
) -> None:
    response = await offline_client.get("/api/memory")

    assert response.status_code == 503
    assert response.json()["detail"].startswith("the database is not reachable")
