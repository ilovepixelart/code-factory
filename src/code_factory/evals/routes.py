"""The Agents page's Scorers table: each scorer's answers over 7 and 30 days."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from code_factory.evals.models import Counts
from code_factory.evals.rules import pass_rate
from code_factory.evals.service import JudgeService
from code_factory.platform.web.dependencies import service_of

router = APIRouter(prefix="/api", tags=["evals"])

JudgeDep = Annotated[JudgeService, Depends(service_of(JudgeService))]


def _window(counts: Counts) -> dict[str, Any]:
    return {**counts.model_dump(), "pass_rate": pass_rate(counts)}


@router.get("/scorers", summary="Each repository's scorers and their answers")
async def scorers(judge: JudgeDep) -> dict[str, list[dict[str, Any]]]:
    """One row per `[[scorers]]` entry, in file order; `ticket` is its open filed ticket."""
    rows = await judge.scorer_table()
    return {
        "scorers": [
            {
                "repository": row.repository, "name": row.name, "question": row.question,
                "stage": row.stage, "sample": row.sample, "threshold": row.threshold,
                "week": _window(row.week), "month": _window(row.month), "ticket": row.ticket,
            }
            for row in rows
        ]
    }  # fmt: skip
