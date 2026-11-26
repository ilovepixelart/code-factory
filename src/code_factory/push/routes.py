"""The one item a pushed reply link answers without the sign-in.

A read shows it and changes nothing, since link scanners and notification previews fetch links;
only a press, a POST, answers. Whatever a link cannot do it says in the same words, so a holder
cannot tell a used link from an expired or an unknown one.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc
from code_factory.push.rules import REFUSAL
from code_factory.push.service import PushService
from code_factory.undo.models import Changed

router = APIRouter(prefix="/api/reply", tags=["inbox"])

PushDep = Annotated[PushService, Depends(service_of(PushService))]
GONE: dict[int | str, dict[str, Any]] = {404: problem_doc(f"`{REFUSAL}`.")}


class PressBody(BaseModel):
    """A press for a permission request (`verdict`), or an answer for a question."""

    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: Literal["allow", "deny"] | None = None
    choices: list[str] = []
    answer: str = ""


@router.get("/{token}", summary="What a reply link waits on", responses=GONE)
async def read(token: str, push: PushDep) -> dict[str, Any]:
    """A request's ticket, title, tool, summary and time, or a question's text and choices."""
    return await push.read(token)


@router.post("/{token}", summary="Answer what a reply link waits on", responses=GONE)
async def press(token: str, body: PressBody, push: PushDep) -> Changed:
    """As the Inbox answers it; the link is spent."""
    notice = await push.press(token, body.verdict, body.choices, body.answer)
    return Changed(notice=notice, undo=None)
