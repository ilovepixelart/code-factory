import httpx
from fastapi import FastAPI

from code_factory.platform.config import Settings
from code_factory.platform.web.dependencies import SettingsDep


async def test_the_settings_dependency_is_the_apps_settings(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    @app.get("/api/test/port")
    async def port(settings: SettingsDep) -> dict[str, int]:
        return {"port": settings.port}

    assert (await client.get("/api/test/port")).json() == {"port": settings.port}
