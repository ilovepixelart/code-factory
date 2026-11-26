"""A service reaches the database through the unit of work, and its commit is inside the request."""

from typing import Annotated

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import text

from app_lifespan import running_lifespan
from code_factory.app import create_app
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork
from code_factory.platform.web.dependencies import service_of


class FormatService:
    """A stand-in module service: the shape every module service has."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def set(self, value: int, *, fail: bool = False) -> None:
        async with self._uow() as session:
            await session.execute(
                text("update schema_info set data_format_version = :v"), {"v": value}
            )
            if fail:
                msg = "service failed after writing"
                raise RuntimeError(msg)

    async def get(self) -> int:
        async with self._uow() as session:
            return int(
                (
                    await session.execute(text("select data_format_version from schema_info"))
                ).scalar_one()
            )

    async def save_duplicate_deferred(self) -> None:
        """A write whose COMMIT fails: the deferred unique constraint is checked at commit."""
        async with self._uow() as session:
            await session.execute(
                text(
                    "create temp table probe_t (x int unique deferrable initially deferred) "
                    "on commit drop"
                )
            )
            await session.execute(text("insert into probe_t values (1), (1)"))


FormatDep = Annotated[FormatService, Depends(service_of(FormatService))]
router = APIRouter(prefix="/api/test")


@router.post("/format")
async def set_format(service: FormatDep, value: int, fail: bool = False) -> dict[str, str]:
    await service.set(value, fail=fail)
    return {"status": "done"}


@router.get("/format")
async def get_format(service: FormatDep) -> dict[str, int]:
    return {"format": await service.get()}


@router.post("/duplicate")
async def duplicate(service: FormatDep) -> dict[str, str]:
    await service.save_duplicate_deferred()
    return {"status": "saved"}


def _serve(app: FastAPI) -> FastAPI:
    app.include_router(router)
    app.state.services.add(FormatService, FormatService(app.state.resources.uow))
    return app


@pytest.fixture
def routes(app: FastAPI) -> FastAPI:
    return _serve(app)


@pytest.mark.usefixtures("routes")
async def test_a_write_is_visible_to_the_next_request(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/test/format", params={"value": 41})).json() == {
        "status": "done"
    }
    assert (await client.get("/api/test/format")).json() == {"format": 41}


@pytest.mark.usefixtures("routes")
async def test_a_service_that_raises_leaves_nothing_written(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/test/format", params={"value": 41, "fail": "true"})
    assert (response.status_code, response.json()["detail"]) == (500, "internal error")
    assert (await client.get("/api/test/format")).json() == {"format": 1}


async def test_a_commit_that_fails_answers_500_not_200(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    app = _serve(
        create_app(settings, guarded=False)
    )  # real sessions: the deferred constraint is checked at COMMIT
    async with running_lifespan(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            response = await client.post("/api/test/duplicate")
    assert (response.status_code, response.json()["detail"]) == (500, "internal error")
