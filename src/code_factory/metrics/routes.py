"""The Flow page: how work moved through the columns over a range."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from code_factory.metrics.models.reports import FlowPage, StepTime
from code_factory.metrics.rules.stages import range_of
from code_factory.metrics.service import MetricsService
from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc
from code_factory.talk.models import QuestionWait
from code_factory.talk.service import TalkService

router = APIRouter(prefix="/api", tags=["metrics"])

MetricsDep = Annotated[MetricsService, Depends(service_of(MetricsService))]
TalkDep = Annotated[TalkService, Depends(service_of(TalkService))]
Range = Literal["24h", "7d", "30d", "90d"]

GATE_BUDGET_SECONDS = {
    "prepare": 15,
    "test-delta": 5,
    "spec-lock": 5,
    "secrets": 10,
    "audit": 30,
    "static": 30,
    "affected-python": 30,
    "affected-web": 45,
    "pytest": 130,
    "web": 90,
    "build": 30,
    "diff-coverage": 5,
    "semgrep": 60,
    "mutation": 180,
}


class GateTiming(StepTime):
    """A board check step and its advisory budget in seconds."""

    budget: int | None


@router.get("/gate-timings", summary="Gate step timings and advisory budgets")
async def gate_timings(metrics: MetricsDep) -> list[GateTiming]:
    """Summarize up to 25 recent check runs with step results across repositories."""
    return [
        GateTiming(**step.model_dump(), budget=GATE_BUDGET_SECONDS.get(step.step))
        for step in await metrics.step_times(25)
    ]


@router.get("/question-wait", summary="Wait time for an owner's first answer")
async def question_wait(
    talk: TalkDep,
    range: Range | None = None,  # noqa: A002  # the page's own name
) -> QuestionWait:
    """Aggregate the questions that received their first answer in the selected range."""
    now = datetime.now(UTC)
    _, seconds = range_of(range or "")
    return await talk.question_wait(now - timedelta(seconds=seconds), now)


@router.get(
    "/flow",
    summary="Throughput, cycle times and where work waits, over a range",
    responses={400: problem_doc("An unknown range.")},
)
async def flow(
    metrics: MetricsDep,
    range: Range | None = None,  # noqa: A002  # the page's own name
) -> FlowPage:
    """`range` is `24h`, `7d` (the default), `30d` or `90d`; anything else is refused."""
    return await metrics.flow(range)
