"""The Sessions pages: the list, each session's timeline and calls, and their usage."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from code_factory.platform.text.paging import Paging
from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc
from code_factory.sessions.models import StateFilter
from code_factory.sessions.service import SessionService
from code_factory.sessions.service.views import DEFAULT_LAST

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

SessionsDep = Annotated[SessionService, Depends(service_of(SessionService))]
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: problem_doc("No session of that id.")}


@router.get(
    "",
    summary="The agent sessions, waiting ones first, one page at a time",
    responses={400: problem_doc("The page or size is not a whole number in range.")},
)
async def sessions(
    service: SessionsDep,
    page: str | None = None,
    size: str | None = None,
    ended: str | None = None,
    state: StateFilter | None = None,
) -> Any:  # noqa: ANN401  # the list answer the service shapes
    """`page` and `size` (1 to 100) page it; `ended=1` keeps ended sessions; `state` filters."""
    paging = Paging.from_query(page, size)
    return await service.list_sessions(paging, ended=ended == "1", state=state)


@router.get("/usage", summary="Tokens and cost of the named sessions, or of every session")
async def usage(
    service: SessionsDep, session: Annotated[list[str] | None, Query()] = None
) -> dict[str, dict[str, object]]:
    """`session` repeated names them; a session that is not known is left out."""
    return await service.usage(tuple(session or ()))


@router.get(
    "/{session_id}/timeline", summary="One session and its latest events", responses=NOT_FOUND
)
async def timeline(
    session_id: str, service: SessionsDep, last: Annotated[int, Query(ge=1)] = DEFAULT_LAST
) -> Any:  # noqa: ANN401  # the timeline answer the service shapes
    """The `last` events, oldest first."""
    return await service.timeline(session_id, last)


@router.get(
    "/{session_id}/calls/{seq}",
    summary="The input and output of one tool call",
    responses=NOT_FOUND,
)
async def call(session_id: str, seq: int, service: SessionsDep) -> Any:  # noqa: ANN401
    """`seq` is the call's place in the session."""
    return await service.call(session_id, seq)
