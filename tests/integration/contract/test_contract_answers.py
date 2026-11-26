"""Each route served so far answers the shape the web app was written against."""

import httpx
import pytest

from contract_catalogue import PENDING_OWNERS, ROUTES, Route
from contract_shapes import conforms

SERVED_READS = [
    route
    for route in ROUTES
    if route.owner not in PENDING_OWNERS
    and route.method == "GET"
    and route.shape is not None
    and route.example
]


@pytest.mark.parametrize("route", SERVED_READS, ids=lambda route: route.path)
async def test_a_served_read_answers_its_golden_shape(
    client: httpx.AsyncClient, board_ids: dict[str, str], route: Route
) -> None:
    ids = board_ids
    assert route.shape is not None
    response = await client.get(route.example.replace("CF-1", ids["Specs written"]))
    assert response.status_code == 200
    assert conforms(response.json(), route.shape()) == []
