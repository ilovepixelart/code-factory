"""Tracking a repository from the browser, the route beside `code-factory track`."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from code_factory.commands.models import TrackBody
from code_factory.commands.service import RepositoryTracker
from code_factory.platform.web.dependencies import service_of

router = APIRouter(prefix="/api", tags=["repositories"])

TrackerDep = Annotated[RepositoryTracker, Depends(service_of(RepositoryTracker))]


@router.post("/repositories", summary="Track a repository", status_code=201)
async def track(body: TrackBody, tracker: TrackerDep) -> JSONResponse:
    """`path`: an absolute folder in a git repository; its main checkout is tracked.

    Tracking the same checkout again changes nothing; `Location` is the list it is now in.
    """
    record = await tracker.track(body.path)
    return JSONResponse(
        record.model_dump(), status_code=201, headers={"Location": "/api/repositories"}
    )
