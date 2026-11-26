"""The five `/api/factory` routes: the spec's JSON examples, the errors and the null providers."""

import httpx

from code_factory.app import create_app
from code_factory.platform.config import Settings

RANGE = "from=2026-11-01&to=2026-11-08"


async def test_the_factory_is_behind_the_sign_in_guard(offline_settings: Settings) -> None:
    app = create_app(offline_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get(f"/api/factory/dashboard?{RANGE}")
    assert response.status_code == 403
