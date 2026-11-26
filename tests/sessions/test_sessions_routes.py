"""The Sessions routes over HTTP: the refusals each query parameter has."""

import httpx
import pytest

PROBLEM = "application/problem+json"


async def test_an_unknown_sessions_timeline_and_call_are_404(client: httpx.AsyncClient) -> None:
    timeline = await client.get("/api/sessions/no-such-session/timeline")
    call = await client.get("/api/sessions/no-such-session/calls/1")

    assert (timeline.status_code, call.status_code) == (404, 404)
    assert timeline.headers["content-type"] == PROBLEM


@pytest.mark.parametrize(
    ("query", "detail"),
    [("page=0", "page must be a whole number from 1"),
     ("size=101", "size must be a whole number from 1 to 100")],
)  # fmt: skip
async def test_a_page_out_of_range_is_400_with_its_rule(
    client: httpx.AsyncClient, query: str, detail: str
) -> None:
    response = await client.get(f"/api/sessions?{query}")

    assert response.status_code == 400
    assert response.json()["detail"] == detail


@pytest.mark.parametrize(
    ("path", "pointer"),
    [("/api/sessions?state=sleeping", "/query/state"),
     ("/api/sessions/s1/timeline?last=0", "/query/last"),
     ("/api/sessions/s1/calls/first", "/path/seq")],
)  # fmt: skip
async def test_a_parameter_of_the_wrong_kind_is_400_pointing_at_it(
    client: httpx.AsyncClient, path: str, pointer: str
) -> None:
    response = await client.get(path)

    assert response.status_code == 400
    assert [e["pointer"] for e in response.json()["errors"]] == [pointer]


async def test_usage_of_no_known_session_is_empty(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/sessions/usage?session=nobody&session=none")

    assert (response.status_code, response.json()) == (200, {})
