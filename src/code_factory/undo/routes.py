"""Taking a change back from the notice that offered it."""

from typing import Annotated

from fastapi import APIRouter, Depends

from code_factory.platform.web.dependencies import service_of
from code_factory.undo.models import Changed
from code_factory.undo.service import UndoService

router = APIRouter(prefix="/api", tags=["undo"])

UndoDep = Annotated[UndoService, Depends(service_of(UndoService))]
OWNER = "owner:owner"


@router.post("/undo/{token}", summary="Take a change back")
async def undo(token: str, service: UndoDep) -> Changed:
    """Once, within 30 seconds of the change; 410 `nothing to undo any more` after."""
    return await service.undo(token, OWNER)
