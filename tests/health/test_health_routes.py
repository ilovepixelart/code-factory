import asyncio
import time
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI

from code_factory.health.service import ReadinessService
from code_factory.platform.config import Settings
from code_factory.platform.db import create_engine


async def test_health_answers_without_any_database(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/api/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


async def test_ready_answers_when_the_database_does(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/ready")
    assert (response.status_code, response.json()) == (200, {"status": "ready"})


async def test_ready_says_503_with_the_reason_when_the_database_refuses_connections(
    client: httpx.AsyncClient, app: FastAPI, offline_settings: Settings
) -> None:
    engine = create_engine(offline_settings)  # port 1: nothing listens
    app.state.services.add(ReadinessService, ReadinessService(engine, timeout_s=2.0))
    try:
        response = await client.get("/api/ready")
    finally:
        await engine.dispose()
    assert response.status_code == 503
    assert response.json()["detail"] == "the database is not reachable (ConnectionRefusedError)"
    assert "not-a-password" not in response.text


@pytest.fixture
async def silent_server() -> AsyncGenerator[int]:
    """A TCP server that accepts connections and never answers."""
    held: list[asyncio.StreamWriter] = []

    async def accept(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        held.append(writer)

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    try:
        yield int(server.sockets[0].getsockname()[1])
    finally:
        server.close()
        for writer in held:
            writer.close()
        await server.wait_closed()


async def test_ready_says_503_when_the_database_does_not_answer_in_time(
    client: httpx.AsyncClient, app: FastAPI, silent_server: int
) -> None:
    settings = Settings(
        database_url=f"postgresql+asyncpg://u:p@127.0.0.1:{silent_server}/x_test",
        _env_file=None,
    )
    engine = create_engine(settings)
    app.state.services.add(ReadinessService, ReadinessService(engine, timeout_s=0.2))
    started = time.monotonic()
    try:
        response = await client.get("/api/ready")
    finally:
        await engine.dispose()
    elapsed = time.monotonic() - started
    assert response.status_code == 503
    assert response.json()["detail"] == "the database did not answer within 0.2 s"
    assert elapsed < 2  # the connect timeout is 10 s: only the readiness deadline ends this early
