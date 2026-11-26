"""The Agents page's routes over HTTP: the roster with what each does, changes and connections."""

from pathlib import Path

import httpx
import pytest

AGENT = "route-builder"


async def test_local_harnesses_report_trusted_executables_only(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def find(name: str, _excluded: tuple[Path, ...]) -> Path | None:
        return Path("/opt/homebrew/bin") / name if name in {"codex", "srt"} else None

    monkeypatch.setattr("code_factory.agents.service.roster.find_program", find)

    response = await client.get("/api/harnesses")

    assert response.status_code == 200
    assert response.json() == {"claude": False, "codex": True, "srt": True}


async def test_an_added_agent_is_listed_with_the_rosters_live_facts(
    client: httpx.AsyncClient,
) -> None:
    added = await client.post("/api/agent-definitions", json={"name": AGENT, "roles": ["build"]})
    listed = (await client.get("/api/agent-definitions")).json()

    assert added.status_code == 200
    assert set(added.json()) == {"notice", "undo"}
    assert AGENT in [agent["name"] for agent in listed["agents"]]
    assert (listed["doing"], listed["last"], listed["starting"]) == ({}, {}, False)


async def test_an_edit_changes_only_the_fields_given_and_a_removal_takes_it_off(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/api/agent-definitions", json={"name": AGENT, "roles": ["build"]})

    edited = await client.patch(f"/api/agent-definitions/{AGENT}", json={"model": "opus"})
    after = (await client.get("/api/agent-definitions")).json()["agents"]
    removed = await client.delete(f"/api/agent-definitions/{AGENT}")
    gone = (await client.get("/api/agent-definitions")).json()["agents"]

    assert edited.status_code == 200
    [agent] = [a for a in after if a["name"] == AGENT]
    assert (agent["model"], agent["roles"]) == ("opus", ["build"])
    assert removed.status_code == 200
    assert AGENT not in [a["name"] for a in gone]


async def test_an_unknown_field_is_refused_and_points_at_it(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/agent-definitions", json={"name": AGENT, "colour": "red"})

    assert response.status_code == 400
    assert [e["pointer"] for e in response.json()["errors"]] == ["/body/colour"]


async def test_changing_an_agent_that_is_not_defined_is_404(client: httpx.AsyncClient) -> None:
    response = await client.patch("/api/agent-definitions/nobody-here", json={"model": "opus"})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


async def test_a_connection_is_added_and_listed_without_its_key(client: httpx.AsyncClient) -> None:
    added = await client.post(
        "/api/connections",
        json={"name": "route-cloud", "kind": "openrouter", "key_env": "OPENROUTER_API_KEY"},
    )
    listed = (await client.get("/api/connections")).json()

    assert added.status_code == 200
    [connection] = [c for c in listed["connections"] if c["name"] == "route-cloud"]
    assert "sk-" not in str(connection)
    assert {k["kind"] for k in listed["kinds"]} >= {"openrouter"}
