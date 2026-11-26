"""Factory output and model performance: read-only figures over a range.

`from` and `to` are epoch seconds, a UTC date (`2026-11-01` is midnight) or an RFC 3339 instant;
both are optional (the range defaults to the last 30 days up to now).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from code_factory.factory.models import (
    Dashboard,
    ExpensiveList,
    Improvements,
    RunBreakdowns,
    Scorers,
)
from code_factory.factory.service import FactoryService
from code_factory.platform.web.dependencies import service_of

router = APIRouter(
    prefix="/api/factory",
    tags=["factory"],
    responses={
        400: {"description": "The range or the limit is not valid."},
        503: {"description": "A provider of the figures cannot answer."},
    },
)

FactoryDep = Annotated[FactoryService, Depends(service_of(FactoryService))]
FromQuery = Annotated[str | None, Query(alias="from", description="Start of the range, included.")]
ToQuery = Annotated[str | None, Query(description="End of the range, excluded.")]
LimitQuery = Annotated[str | None, Query(description="How many to list, from 1 to 50.")]


@router.get("/dashboard", summary="Every figure of the factory page for a range")
async def dashboard(service: FactoryDep, from_: FromQuery = None, to: ToQuery = None) -> Dashboard:
    """Runs, pull requests, cycle time, cost, scorers and improvements in one answer."""
    return await service.dashboard(from_, to)


@router.get("/runs", summary="Runs of a range counted by stage, state, source, model and agent")
async def runs(service: FactoryDep, from_: FromQuery = None, to: ToQuery = None) -> RunBreakdowns:
    """The `runs` object of the dashboard."""
    return await service.runs(from_, to)


@router.get("/prs/expensive", summary="The most expensive pull requests of a range")
async def expensive(
    service: FactoryDep, from_: FromQuery = None, to: ToQuery = None, limit: LimitQuery = None
) -> ExpensiveList:
    """Priced pull requests opened in the range, dearest first (10 by default)."""
    return await service.expensive(from_, to, limit)


@router.get("/scorers", summary="Scorer results for a range")
async def scorers(service: FactoryDep, from_: FromQuery = None, to: ToQuery = None) -> Scorers:
    """One card per scorer: its answers, pass rate and the window they were counted over."""
    return await service.scorers(from_, to)


@router.get("/improvements", summary="The newest self-improvement pull requests")
async def improvements(service: FactoryDep, limit: LimitQuery = None) -> Improvements:
    """The newest ones whatever the range (3 by default)."""
    return await service.improvements(limit)
