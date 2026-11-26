"""The Team page and the agents' lanes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from code_factory.platform.web.dependencies import service_of
from code_factory.team.service import TeamService

router = APIRouter(prefix="/api", tags=["team"])

TeamDep = Annotated[TeamService, Depends(service_of(TeamService))]


@router.get("/team/now", summary="What needs the owner, waits, works and merged today")
async def team_now(team: TeamDep) -> dict[str, Any]:
    """The Team page."""
    return (await team.now()).model_dump(by_alias=True, mode="json")


@router.get("/team", summary="The agents' lanes over the last six hours")
async def team_lanes(team: TeamDep) -> dict[str, Any]:
    """One lane per agent, with the chains of runs between tickets."""
    return (await team.lanes()).model_dump(by_alias=True, mode="json")
