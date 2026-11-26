"""The hook routes over HTTP, with real tokens: who may call, and a request the owner answers."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app_lifespan import IDLE_MODULES, running_lifespan
from code_factory.app import create_app
from code_factory.auth.service import AuthService
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory
from code_factory.repositories.service import RepositoryService
from code_factory.runs.repository import RunRepository
from code_factory.runs.service import PermissionService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService
from runs_values import a_run

HOUR = timedelta(hours=1)


@dataclass
class Board:
    app: FastAPI
    client: httpx.AsyncClient
    run_token: str
    owner_token: str
    ticket: str


@pytest.fixture
async def board(
    settings: Settings,
    serve_env: dict[str, str],
    tmp_path: Path,
) -> AsyncGenerator[Board]:
    """Use pooled connections in a private schema so committed hook rows stay isolated."""
    own = settings.model_copy(
        update={"db_schema": serve_env["CODE_FACTORY_DB_SCHEMA"], "state_dir": tmp_path / "state"}
    )
    app = create_app(own, modules=IDLE_MODULES)
    engine = create_engine(own)
    run_id = uuid.uuid4().hex[:12]
    async with (
        running_lifespan(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client,
    ):
        services = app.state.services
        root = tmp_path / "sample"
        root.mkdir()
        await services.get(RepositoryService).track(root)
        ticket = await services.get(TicketService).create(
            NewTicket(repository="sample", title="Hooked"), by="owner"
        )
        async with UnitOfWork(create_session_factory(engine))() as session:
            await RunRepository(session).insert(a_run(ticket.number, run_id=run_id))
        auth = services.get(AuthService)
        run = await auth.issue_run_token(
            run_id=run_id, ticket_id=ticket.id, stage="build", repository="sample", lifetime=HOUR
        )
        owner = await auth.issue_owner_token("hooks", lifetime=HOUR)
        try:
            yield Board(
                app, client, run.token.get_secret_value(), owner.token.get_secret_value(), ticket.id
            )
        finally:
            await engine.dispose()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_a_hook_without_a_known_token_is_401_and_with_one_is_answered(board: Board) -> None:
    body = {"cwd": "/nowhere", "session_id": "s"}
    none = await board.client.post("/api/hooks/recall", json=body)
    wrong = await board.client.post("/api/hooks/recall", json=body, headers=_bearer("cfo_x"))
    owner = await board.client.post(
        "/api/hooks/recall", json=body, headers=_bearer(board.owner_token)
    )

    assert (none.status_code, wrong.status_code) == (401, 401)
    assert (owner.status_code, owner.json()) == (200, {"output": None})


async def test_a_runs_permission_request_waits_for_the_owner_and_hears_the_answer(
    board: Board,
) -> None:
    payload = {
        "session_id": "s1", "hook_event_name": "PermissionRequest", "tool_name": "Bash",
        "tool_input": {"command": "curl https://example.com"}, "sandboxed": False,
    }  # fmt: skip
    asked = asyncio.create_task(
        board.client.post("/api/hooks/permission", json=payload, headers=_bearer(board.run_token))
    )
    permissions = board.app.state.services.get(PermissionService)
    for _ in range(200):
        waiting = await permissions.pending(datetime.now(UTC))
        if waiting:
            break
        await asyncio.sleep(0.05)
    [request] = waiting
    await permissions.answer(request.id, allow=True, by="owner:owner")
    answered = await asyncio.wait_for(asked, 30)

    output = json.loads(answered.json()["output"])
    assert output["hookSpecificOutput"]["decision"]["behavior"] == "allow"


async def test_a_run_is_told_through_the_tell_route(board: Board) -> None:
    told = await board.client.post(
        "/api/hooks/tell",
        json={"session_id": "s1", "hook_event_name": "PostToolUse"},
        headers=_bearer(board.run_token),
    )
    assert told.status_code == 200
    assert set(told.json()) == {"output", "confirm"}
