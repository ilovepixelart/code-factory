"""What an agent's hooks ask the board over loopback HTTP, with the run's or the owner's token.

These paths pass the owner's cookie guard: a hook has no browser session, so each route checks
the bearer token itself and answers 401 without one the board knows.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from code_factory.auth.service import AuthService
from code_factory.hooks.models import TellAnswer
from code_factory.hooks.service import HookService
from code_factory.platform.identity import Actor
from code_factory.platform.web.dependencies import service_of

router = APIRouter(prefix="/api/hooks", tags=["hooks"])

HooksDep = Annotated[HookService, Depends(service_of(HookService))]
AuthDep = Annotated[AuthService, Depends(service_of(AuthService))]
NO_TOKEN = "a hook call needs the run's or the owner's token as a bearer token"  # noqa: S105  # a sentence
SCHEME = "bearer "


async def _actor(auth: AuthDep, authorization: Annotated[str, Header()] = "") -> Actor:
    if not authorization.lower().startswith(SCHEME):
        raise HTTPException(401, NO_TOKEN)
    actor = await auth.verify_token(authorization[len(SCHEME) :].strip())
    if actor is None:
        raise HTTPException(401, NO_TOKEN)
    return actor


ActorDep = Annotated[Actor, Depends(_actor)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TellBody(_Body):
    """The session a tool result came from."""

    session_id: str = ""
    hook_event_name: str = ""


class ConfirmBody(_Body):
    """The marks the tell answered, once the session printed them."""

    session_id: str
    confirm: dict[str, Any]


class RecallBody(_Body):
    """The folder a session starts in."""

    cwd: str
    session_id: str = ""


class Output(BaseModel):
    """The text the hook prints; none prints nothing."""

    output: str | None = None


@router.post("/tell", summary="What was said on the run's ticket since it last heard")
async def tell(body: TellBody, actor: ActorDep, hooks: HooksDep) -> TellAnswer:
    """The hook text and the marks to confirm it with, once printed."""
    return await hooks.tell(actor, body.model_dump())


@router.post("/tell/confirm", summary="Mark what a session was told as delivered")
async def confirm(body: ConfirmBody, actor: ActorDep, hooks: HooksDep) -> dict[str, Any]:
    """`confirm` is the `confirm` the tell answered."""
    await hooks.confirm_tell(actor, body.session_id, body.confirm)
    return {}


@router.post("/permission", summary="A run's permission request, settled by rule or the owner")
async def permission(
    request: Request, payload: dict[str, Any], actor: ActorDep, hooks: HooksDep
) -> Output:
    """Waits while the owner decides; a closed hook withdraws the request."""

    async def alive() -> bool:
        return not await request.is_disconnected()

    sandboxed = payload.pop("sandboxed", False) is True
    text = await hooks.permission(actor, payload, sandboxed=sandboxed, alive=alive)
    return Output(output=text)


@router.post("/recall", summary="The standing rules and ticket a session starts with")
async def recall(body: RecallBody, actor: ActorDep, hooks: HooksDep) -> Output:
    """Nothing for a folder outside every tracked repository."""
    found = await hooks.recall(cwd=body.cwd, actor=actor)
    return Output(output=None if found is None else found.text)
