"""Liveness and readiness probes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from code_factory.health.models import Health, Ready
from code_factory.health.service import ReadinessService
from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc

router = APIRouter(prefix="/api", tags=["health"])

ReadinessDep = Annotated[ReadinessService, Depends(service_of(ReadinessService))]


@router.get("/health", summary="Liveness: the process is up (no database)")
async def health() -> Health:
    """Answers whenever the event loop does."""
    return Health(status="ok")


@router.get(
    "/ready",
    summary="Readiness: the database answers",
    responses={503: problem_doc("The database is not reachable.")},
)
async def ready(readiness: ReadinessDep) -> Ready:
    """Pings the database within the ready timeout."""
    await readiness.check()
    return Ready(status="ready")
