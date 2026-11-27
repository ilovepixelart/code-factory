"""The evals services over a real database with fake repositories and tickets."""

from datetime import UTC, date, datetime, timedelta

import pytest

from code_factory.evals.models import (
    Answer,
    AnswerRow,
    EvalRecord,
    Filed,
    Kind,
    Role,
    Scorer,
    Setup,
    StartedBy,
    TaskRun,
)
from code_factory.evals.service import EvalService, JudgeService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError

NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)


class Places:
    def __init__(self) -> None:
        self.listed = [Scorer(name="ran-tests", question="Did it run the tests?", threshold=2)]

    async def names(self) -> list[str]:
        return ["sample"]

    async def scorers(self, repository: str) -> list[Scorer]:  # noqa: ARG002
        return self.listed


class Tickets:
    def __init__(self) -> None:
        self.filed: list[Filed] = []


class _Tickets:
    def __init__(self, tickets: Tickets) -> None:
        self._tickets = tickets

    async def filed(self, repository: str) -> list[Filed]:  # noqa: ARG002
        return self._tickets.filed


@pytest.fixture
def tickets() -> Tickets:
    return Tickets()


@pytest.fixture
def judge(uow: UnitOfWork, tickets: Tickets) -> JudgeService:
    return JudgeService(uow, Places(), _Tickets(tickets), clock=lambda: NOW)


def _answer(session: str, answer: Answer, days_ago: float) -> AnswerRow:
    return AnswerRow(
        session_id=session,
        scorer="ran-tests",
        answer=answer,
        evidence="it ran pytest",
        at=NOW - timedelta(days=days_ago),
    )


async def test_a_record_reads_back_with_its_task_runs(uow: UnitOfWork) -> None:
    evals = EvalService(uow)
    runs = (
        TaskRun(task_id="t1", run_no=1, role=Role.BUILD, passed=True),
        TaskRun(task_id="t1", run_no=2, role=Role.BUILD, passed=False),
    )
    record = EvalRecord(
        repository="sample", set_name="smoke", kind=Kind.BUILD, recorded_at=NOW,
        setup=Setup(runtime="claude -p {prompt}", model="opus", instructions="abc"), runs=2,
        pass_at_1=0.5, pass_k=0.0, pass_at_k=1.0, cost=0.5, task_runs=runs,
    )  # fmt: skip

    await evals.record(record)

    [back] = await evals.records("sample", "smoke")
    assert back.task_runs == runs
    line = (
        "build: claude opus instructions abc: 2 runs per task, pass@1 50%, pass@k 100%,"
        " pass^k 0%, $0.50"
    )
    assert await evals.report("sample", "smoke") == [line]


async def test_a_set_name_with_a_path_is_refused(uow: UnitOfWork) -> None:
    evals = EvalService(uow)
    with pytest.raises(BadRequestError, match="is not a task set name"):
        await evals.report("sample", "../x")


async def test_the_scorer_table_counts_the_week_and_the_month(judge: JudgeService) -> None:
    for session, answer, days in [("a", Answer.YES, 1), ("b", Answer.NO, 2), ("c", Answer.NO, 20)]:
        await judge.record_answer("sample", _answer(session, answer, days))

    [row] = await judge.scorer_table()

    assert (row.week.yes, row.week.no, row.month.no) == (1, 1, 2)
    assert row.ticket == ""


async def test_a_scorer_past_its_threshold_is_due_and_names_the_open_ticket_after(
    judge: JudgeService, tickets: Tickets
) -> None:
    await judge.record_answer("sample", _answer("a", Answer.NO, 2))
    await judge.record_answer("sample", _answer("b", Answer.NO, 1))

    [firing] = await judge.scorer_firings("sample")
    tickets.filed.append(Filed(source=firing.source, open=True, id="CF-9"))

    assert firing.title == "Scorer ran-tests: 2 sessions answered no"
    assert await judge.scorer_firings("sample") == []
    assert (await judge.scorer_table())[0].ticket == "CF-9"


async def test_a_judge_day_is_claimed_once(judge: JudgeService) -> None:
    day = date(2026, 11, 20)
    assert await judge.claim_day("sample", day)
    assert not await judge.claim_day("sample", day)


async def test_scheduled_spend_counts_only_this_months_scheduled_rows(judge: JudgeService) -> None:
    await judge.record_score("sample", "s1", 4, [], cost=0.25, by=StartedBy.SCHEDULE)
    await judge.record_score("sample", "s2", 3, [], cost=1.0, by=StartedBy.OWNER)

    assert await judge.scheduled_spent("sample") == 0.25


async def test_a_score_outside_one_to_five_is_refused(judge: JudgeService) -> None:
    with pytest.raises(BadRequestError, match="1 to 5, not 6"):
        await judge.record_score("sample", "s1", 6, [])


async def test_an_eval_receipt_is_idempotent_and_its_cost_is_counted_once(
    uow: UnitOfWork, judge: JudgeService
) -> None:
    evals = EvalService(uow)
    raw = {
        "repository": "sample",
        "set_name": "smoke",
        "kind": "build",
        "recorded_at": NOW,
        "setup": {"runtime": "codex", "model": "review-model"},
        "runs": 1,
        "pass_at_1": 1.0,
        "pass_k": 1.0,
        "pass_at_k": 1.0,
        "receipt": "run-2026-11-20-001",
        "cost": 0.0,
    }
    receipt = EvalRecord.model_validate(raw)
    start, end = NOW, NOW + timedelta(days=1)
    assert await evals.record(receipt) == await evals.record(receipt)
    assert await evals.measurement_spend(start, end) == 0.0

    with pytest.raises(ConflictError, match="different result"):
        await evals.record(receipt.model_copy(update={"cost": 2.0}))

    await judge.record_score("sample", "s1", 4, [], cost=1.25)
    await judge.record_score("sample", "s2", 4, [])
    assert await evals.measurement_spend(start, end) == 1.25
    assert await evals.measurement_spend(start - timedelta(days=1), start) is None
