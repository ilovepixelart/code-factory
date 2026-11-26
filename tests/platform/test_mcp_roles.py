"""A listener may accept only some roles: the runner's address takes run tokens only."""

from datetime import UTC, datetime

import httpx2
import pytest

from code_factory.platform.config import Settings
from code_factory.platform.identity import Actor, Role
from code_factory.platform.mcp import Access
from code_factory.platform.mcp.http import build_mcp_app
from code_factory.platform.services import Services

EXPIRES = datetime(2999, 1, 1, tzinfo=UTC)
RUN = Actor(
    role=Role.RUN,
    subject="run:r1",
    token_id=1,
    run_id="r1",
    ticket_id="CF-1",
    stage="build",
    repository="/r",
    expires_at=EXPIRES,
)
OWNER = Actor(role=Role.OWNER, subject="owner:a", token_id=2, expires_at=EXPIRES)
TOKENS = {"cfr_" + "r" * 43: RUN, "cfo_" + "o" * 43: OWNER}


class Known:
    async def verify_token(self, token: str) -> Actor | None:
        return TOKENS.get(token)


async def _status(roles: frozenset[Role] | None, token: str, settings: Settings) -> int:
    app = build_mcp_app(Services(), [], settings, Access(verifier=Known(), roles=roles))
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as http,
    ):
        response = await http.post(
            "/",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={
                "accept": "application/json, text/event-stream",
                "authorization": f"Bearer {token}",
            },
        )
    return response.status_code


RUNS_ONLY = frozenset({Role.RUN, Role.COORDINATOR})


@pytest.mark.parametrize(
    ("roles", "token", "refused"),
    [
        (RUNS_ONLY, "cfr_" + "r" * 43, False),
        (RUNS_ONLY, "cfo_" + "o" * 43, True),
        (None, "cfo_" + "o" * 43, False),
        (frozenset({Role.OWNER}), "cfr_" + "r" * 43, True),
    ],
)
async def test_a_listener_refuses_the_roles_it_does_not_accept_before_any_tool_runs(
    settings: Settings, roles: frozenset[Role] | None, token: str, refused: bool
) -> None:
    status = await _status(roles, token, settings)
    assert (status == 401) is refused
