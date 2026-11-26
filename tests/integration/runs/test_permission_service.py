"""The permission requests of a run: policy, reviewer, owner, and the answers and rules."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, override

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.runs.models import Decision, PermissionRequest, Review
from code_factory.runs.ports import Settings
from code_factory.runs.repository import PermissionRepository, RunRepository
from code_factory.runs.service.permissions import PermissionService
from code_factory.tickets.models import Ticket
from runs_fakes import Fakes
from runs_values import NOW, OWNER, FakeClock, a_run

TREE = "/repo/main/trees/cf-1-0"
RETRY = (
    "Nobody answered this permission request from the board in time; do it another way "
    "inside your worktree, or ask in the ticket's Open questions."
)


class FakeReviewer:
    """The reviewer command: answers with `said` and keeps what it was asked."""

    def __init__(self) -> None:
        self.said: tuple[bool, str] | None = (True, "allow\n")
        self.asked: list[tuple[str, Path, str]] = []
        self.meanwhile: Callable[[], Awaitable[None]] | None = None

    async def __call__(
        self,
        command: str,
        cwd: Path,
        request: str,
        time_s: float = 60.0,  # noqa: ARG002
    ) -> tuple[bool, str] | None:
        self.asked.append((command, cwd, request))
        if self.meanwhile is not None:
            await self.meanwhile()
        return self.said


class OneAtATime(UnitOfWork):
    """The test connection serves one task at a time: a waiter and an answer take turns."""

    def __init__(self, inner: UnitOfWork) -> None:
        self._inner = inner
        self._turn = asyncio.Lock()

    @override
    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[AsyncSession]:
        async with self._turn, self._inner() as session:
            yield session


@pytest.fixture
def one_at_a_time(uow: UnitOfWork) -> UnitOfWork:
    return OneAtATime(uow)


@pytest.fixture
def reviewer() -> FakeReviewer:
    return FakeReviewer()


@pytest.fixture
def perms(
    one_at_a_time: UnitOfWork, fakes: Fakes, clock: FakeClock, reviewer: FakeReviewer
) -> PermissionService:
    return PermissionService(one_at_a_time, fakes.config, clock=clock, reviewer=reviewer, poll_s=30)


@pytest.fixture
async def run_id(db_session: AsyncSession, ticket: Ticket) -> str:
    await RunRepository(db_session).insert(a_run(ticket.number, worktree=TREE))
    return "a1b2c3d4e5f6"


@pytest.fixture
def reviewed(fakes: Fakes, reviewer: FakeReviewer) -> FakeReviewer:
    """The reviewer, configured for the repository."""
    fakes.config.value = Settings(permission_reviewer="review.sh")
    return reviewer


def call(tool: str = "Bash", **fields: object) -> dict[str, object]:
    return {"tool_name": tool, "tool_input": fields, "session_id": "s1"}


def behavior(output: dict[str, Any]) -> dict[str, Any]:
    return output["hookSpecificOutput"]["decision"]


async def waiting(perms: PermissionService) -> PermissionRequest:
    for _ in range(200):
        if pending := await perms.pending(NOW):
            return pending[0]
        await asyncio.sleep(0.01)
    msg = "no request is waiting"
    raise AssertionError(msg)


async def test_the_policy_refuses_a_read_outside_the_tree_and_does_not_interrupt(
    perms: PermissionService, run_id: str
) -> None:
    out = await perms.request(run_id, call("Read", file_path="/etc/hosts"), wait=1)
    assert behavior(out) == {
        "behavior": "deny",
        "message": "/etc/hosts is outside your worktree " + TREE + "; use paths inside it",
    }
    assert await perms.pending(NOW) == []


async def test_the_policy_allows_a_read_only_board_tool(
    perms: PermissionService, run_id: str
) -> None:
    out = await perms.request(run_id, call("mcp__code-factory__search_memory", query="x"), wait=1)
    assert behavior(out) == {"behavior": "allow"}


async def test_the_fourth_refusal_in_a_row_goes_to_the_owner_with_the_policy_words(
    perms: PermissionService, run_id: str
) -> None:
    for _ in range(3):
        await perms.request(run_id, call("Read", file_path="/etc/hosts"), wait=1)
    task = asyncio.create_task(perms.request(run_id, call("Read", file_path="/etc/hosts"), wait=5))
    pending = await waiting(perms)
    assert pending.note == (
        "the board's policy refused 3 requests in a row: "
        f"/etc/hosts is outside your worktree {TREE}; use paths inside it"
    )
    await perms.answer(pending.id, allow=True, by=OWNER)
    assert behavior(await task) == {"behavior": "allow"}


async def test_an_owner_allow_answers_the_waiting_hook(
    perms: PermissionService, run_id: str
) -> None:
    task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(perms)
    assert (pending.tool, pending.summary, pending.kind) == (
        "Bash",
        "git status",
        "Bash(git status *)",
    )
    answered = await perms.answer(pending.id, allow=True, by=OWNER)
    assert (answered.status, answered.verdict, answered.answered_by) == ("answered", "allow", OWNER)
    assert behavior(await task) == {"behavior": "allow"}


async def test_an_owner_deny_interrupts_the_run(perms: PermissionService, run_id: str) -> None:
    task = asyncio.create_task(perms.request(run_id, call(command="rm -rf x"), wait=5))
    pending = await waiting(perms)
    await perms.answer(pending.id, allow=False, by=OWNER)
    assert behavior(await task) == {
        "behavior": "deny",
        "message": "The owner denied this request.",
        "interrupt": True,
    }


async def test_an_unanswered_request_returns_the_retry_words_and_is_withdrawn(
    perms: PermissionService, run_id: str
) -> None:
    out = await perms.request(run_id, call(command="git status"), wait=0.05)
    assert behavior(out) == {"behavior": "deny", "message": RETRY}
    assert await perms.pending(NOW) == []


async def test_a_late_answer_to_a_withdrawn_request_is_refused(
    perms: PermissionService, run_id: str, db_session: AsyncSession
) -> None:
    task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(perms)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(NotFoundError, match="the agent stopped waiting for this answer"):
        await perms.answer(pending.id, allow=True, by=OWNER)
    found = await PermissionRepository(db_session).get_request(pending.id)
    assert found is not None
    assert found.status == "withdrawn"


async def test_a_second_answer_is_refused(perms: PermissionService, run_id: str) -> None:
    task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(perms)
    await perms.answer(pending.id, allow=True, by=OWNER)
    await task
    with pytest.raises(ConflictError, match="this request is already answered"):
        await perms.answer(pending.id, allow=False, by=OWNER)


async def test_an_unknown_request_is_not_found(perms: PermissionService) -> None:
    with pytest.raises(NotFoundError, match="no such permission request"):
        await perms.answer("aaaaaaaaaaaa", allow=True, by=OWNER)


async def test_a_request_older_than_the_wait_cannot_be_answered(
    perms: PermissionService, run_id: str, clock: FakeClock
) -> None:
    task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(perms)
    clock.advance(541)
    with pytest.raises(ConflictError, match="waited longer than 9 minutes"):
        await perms.answer(pending.id, allow=True, by=OWNER)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_request_just_inside_the_wait_can_still_be_answered(
    perms: PermissionService, run_id: str, clock: FakeClock
) -> None:
    task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(perms)
    clock.advance(540)
    assert (await perms.answer(pending.id, allow=True, by=OWNER)).status == "answered"
    await task


async def test_pending_lists_the_oldest_first_and_expires_the_stale(
    perms: PermissionService, run_id: str, clock: FakeClock, db_session: AsyncSession
) -> None:
    repo = PermissionRepository(db_session)
    await repo.add_request(_stored("aaaaaaaaaaaa", clock.now - timedelta(seconds=600)))
    await repo.add_request(_stored("bbbbbbbbbbbb", clock.now - timedelta(seconds=10)))
    await repo.add_request(_stored("cccccccccccc", clock.now - timedelta(seconds=20)))
    assert [r.id for r in await perms.pending(clock.now)] == ["cccccccccccc", "bbbbbbbbbbbb"]
    stale = await repo.get_request("aaaaaaaaaaaa")
    assert stale is not None
    assert stale.status == "expired"
    assert run_id


def _stored(request_id: str, at: object) -> PermissionRequest:
    return PermissionRequest(
        id=request_id,
        repository="sample",
        ticket_key="CF-1",
        tool="Bash",
        summary="git status",
        kind="Bash(git *)",
        requested_at=at,  # ty: ignore[invalid-argument-type]
    )


async def test_an_answer_made_by_another_process_reaches_the_waiter_through_the_row(
    one_at_a_time: UnitOfWork, fakes: Fakes, clock: FakeClock, reviewer: FakeReviewer, run_id: str
) -> None:
    waiter = PermissionService(
        one_at_a_time, fakes.config, clock=clock, reviewer=reviewer, poll_s=0.4
    )
    other = PermissionService(
        one_at_a_time, fakes.config, clock=clock, reviewer=reviewer, poll_s=30
    )
    task = asyncio.create_task(waiter.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(other)
    await asyncio.sleep(0.1)
    await other.answer(pending.id, allow=True, by=OWNER)
    assert behavior(await asyncio.wait_for(task, 3)) == {"behavior": "allow"}


async def test_the_reviewer_allows_before_the_owner_is_asked(
    perms: PermissionService, run_id: str, fakes: Fakes, reviewer: FakeReviewer
) -> None:
    fakes.config.value = Settings(permission_reviewer="review.sh")
    out = await perms.request(run_id, call(command="git status"), wait=1)
    assert behavior(out) == {"behavior": "allow"}
    assert await perms.pending(NOW) == []
    assert reviewer.asked[0][0] == "review.sh"
    assert reviewer.asked[0][1] == Path("/repo/main")
    assert "git status" in reviewer.asked[0][2]


async def test_the_reviewer_denies_with_its_reason_and_no_interrupt(
    perms: PermissionService, run_id: str, fakes: Fakes, reviewer: FakeReviewer
) -> None:
    fakes.config.value = Settings(permission_reviewer="review.sh")
    reviewer.said = (True, "deny writes to main\n")
    out = await perms.request(run_id, call(command="git push"), wait=1)
    assert behavior(out) == {
        "behavior": "deny",
        "message": "The permission reviewer denied this: writes to main",
    }


async def test_a_reviewer_that_cannot_answer_hands_the_request_to_the_owner(
    perms: PermissionService, run_id: str, fakes: Fakes, reviewer: FakeReviewer
) -> None:
    fakes.config.value = Settings(permission_reviewer="review.sh")
    reviewer.said = None
    task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(perms)
    await perms.answer(pending.id, allow=True, by=OWNER)
    assert behavior(await task) == {"behavior": "allow"}


async def test_a_session_past_the_reviewer_limit_goes_to_the_owner(
    perms: PermissionService, run_id: str, fakes: Fakes, reviewer: FakeReviewer
) -> None:
    fakes.config.value = Settings(permission_reviewer="review.sh", permission_reviewer_limit=2)
    for _ in range(2):
        assert behavior(await perms.request(run_id, call(command="git status"), wait=1)) == {
            "behavior": "allow"
        }
    task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(perms)
    assert len(reviewer.asked) == 2
    await perms.answer(pending.id, allow=False, by=OWNER)
    await task


async def test_a_request_over_the_size_limit_is_not_shown_to_the_reviewer(
    perms: PermissionService, run_id: str, fakes: Fakes, reviewer: FakeReviewer
) -> None:
    fakes.config.value = Settings(permission_reviewer="review.sh")
    task = asyncio.create_task(perms.request(run_id, call("Write", content="x" * 70_000), wait=5))
    pending = await waiting(perms)
    assert reviewer.asked == []
    await perms.answer(pending.id, allow=True, by=OWNER)
    await task


async def test_a_request_with_a_note_skips_the_reviewer(
    perms: PermissionService, run_id: str, fakes: Fakes, reviewer: FakeReviewer
) -> None:
    fakes.config.value = Settings(permission_reviewer="review.sh")
    for _ in range(3):
        await perms.request(run_id, call("Read", file_path="/etc/hosts"), wait=1)
    task = asyncio.create_task(perms.request(run_id, call("Read", file_path="/etc/hosts"), wait=5))
    pending = await waiting(perms)
    assert reviewer.asked == []
    await perms.answer(pending.id, allow=False, by=OWNER)
    await task


async def test_a_kind_allowed_five_times_is_suggested_and_once_adopted_is_allowed_unasked(
    perms: PermissionService, run_id: str
) -> None:
    assert await perms.suggested() == []
    for _ in range(5):
        task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
        pending = await waiting(perms)
        await perms.answer(pending.id, allow=True, by=OWNER)
        await task
    assert await perms.suggested() == [("Bash(git status *)", 5)]
    assert await perms.answered_counts() == {"Bash(git status *)": (5, 5)}
    assert await perms.adopt_rule("Bash(git status *)") is True
    assert await perms.rules() == ["Bash(git status *)"]
    assert await perms.suggested() == []
    out = await perms.request(run_id, call(command="git status -s"), wait=1)
    assert behavior(out) == {"behavior": "allow"}
    assert await perms.pending(NOW) == []


async def test_a_kind_allowed_four_times_is_not_suggested_and_cannot_be_adopted(
    perms: PermissionService, run_id: str
) -> None:
    for _ in range(4):
        task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
        pending = await waiting(perms)
        await perms.answer(pending.id, allow=True, by=OWNER)
        await task
    assert await perms.suggested() == []
    with pytest.raises(ConflictError, match="that is not a suggested rule"):
        await perms.adopt_rule("Bash(git status *)")


async def test_decisions_are_the_latest_on_the_ticket_oldest_first(
    perms: PermissionService, run_id: str, ticket: Ticket
) -> None:
    await perms.request(run_id, call("Read", file_path="/etc/hosts"), wait=1)
    await perms.request(run_id, call("mcp__code-factory__search_memory", query="x"), wait=1)
    found = await perms.decisions("sample", ticket.id)
    assert [(d.by, d.decision) for d in found] == [("policy", "deny"), ("policy", "allow")]
    assert isinstance(found[0], Decision)


async def test_a_request_of_an_unknown_run_is_not_found(perms: PermissionService) -> None:
    given = call(command="ls")
    with pytest.raises(NotFoundError, match="no such run"):
        await perms.request("ffffffffffff", given, wait=1)


async def test_decisions_older_than_ninety_days_are_pruned(
    perms: PermissionService, run_id: str, clock: FakeClock
) -> None:
    await perms.request(run_id, call("Read", file_path="/etc/hosts"), wait=1)
    clock.advance(90 * 86400 - 1)
    assert await perms.prune(clock.now) == 0
    clock.advance(2)
    assert await perms.prune(clock.now) == 1


async def test_an_allow_that_arrives_after_the_session_limit_filled_goes_to_the_owner(
    perms: PermissionService,
    run_id: str,
    fakes: Fakes,
    reviewer: FakeReviewer,
    one_at_a_time: UnitOfWork,
) -> None:
    fakes.config.value = Settings(permission_reviewer="review.sh", permission_reviewer_limit=2)

    async def two_other_reviews_land() -> None:
        async with one_at_a_time() as session:
            repo = PermissionRepository(session)
            for _ in range(2):
                await repo.record_review(
                    Review(
                        at=NOW,
                        session_id="s1",
                        ticket_key="CF-1",
                        tool="Bash",
                        summary="x",
                        input_sha256="0" * 64,
                        verdict="allow",
                    )
                )

    reviewer.meanwhile = two_other_reviews_land
    task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(perms)
    await perms.answer(pending.id, allow=False, by=OWNER)
    assert behavior(await task)["behavior"] == "deny"


async def test_an_allow_that_arrives_after_a_denial_of_the_session_goes_to_the_owner(
    perms: PermissionService,
    run_id: str,
    reviewed: FakeReviewer,
    one_at_a_time: UnitOfWork,
    ticket: Ticket,
) -> None:

    async def a_denial_lands() -> None:
        async with one_at_a_time() as session:
            await PermissionRepository(session).record_review(
                Review(
                    at=NOW,
                    session_id="s1",
                    ticket_key="CF-1",
                    tool="Bash",
                    summary="x",
                    input_sha256="0" * 64,
                    verdict="deny",
                )
            )

    reviewed.meanwhile = a_denial_lands
    task = asyncio.create_task(perms.request(run_id, call(command="git status"), wait=5))
    pending = await waiting(perms)
    await perms.answer(pending.id, allow=False, by=OWNER)
    assert behavior(await task)["behavior"] == "deny"
    assert [d.by for d in await perms.decisions("sample", ticket.id)] == ["owner"]


async def test_a_sandboxed_shell_command_is_allowed_by_the_policy_and_recorded(
    perms: PermissionService, run_id: str, ticket: Ticket
) -> None:
    out = await perms.request(run_id, call(command="npm test"), wait=1, sandboxed=True)

    assert behavior(out) == {"behavior": "allow"}
    assert await perms.pending(NOW) == []
    (decision,) = await perms.decisions("sample", ticket.id)
    assert (decision.by, decision.decision, decision.reason) == (
        "policy",
        "allow",
        "a command inside the run's sandbox",
    )


async def test_a_shell_command_outside_the_sandbox_still_goes_to_the_owner(
    perms: PermissionService, run_id: str
) -> None:
    out = await perms.request(run_id, call(command="npm test"), wait=0.05, sandboxed=False)

    assert behavior(out) == {"behavior": "deny", "message": RETRY}


async def test_the_sandbox_allows_only_shell_commands(
    perms: PermissionService, run_id: str
) -> None:
    out = await perms.request(
        run_id, call("Write", file_path="/x/y", content="z"), wait=0.05, sandboxed=True
    )

    assert behavior(out) == {"behavior": "deny", "message": RETRY}


async def test_a_sandboxed_command_goes_to_the_reviewer_a_repository_names(
    perms: PermissionService, run_id: str, fakes: Fakes, reviewer: FakeReviewer
) -> None:
    fakes.config.value = Settings(permission_reviewer="review.sh")
    reviewer.said = (True, "deny not that\n")

    out = await perms.request(run_id, call(command="git push"), wait=1, sandboxed=True)

    assert behavior(out) == {
        "behavior": "deny",
        "message": "The permission reviewer denied this: not that",
    }
    assert len(reviewer.asked) == 1


async def test_the_policy_refusal_of_a_path_outside_the_tree_wins_in_the_sandbox(
    perms: PermissionService, run_id: str
) -> None:
    out = await perms.request(run_id, call(command="cat /repo/main/x"), wait=1, sandboxed=True)

    assert behavior(out)["behavior"] == "deny"
    assert "outside your worktree" in behavior(out)["message"]


async def test_a_decision_a_caller_makes_is_recorded_on_the_ticket(
    perms: PermissionService, run_id: str, ticket: Ticket
) -> None:
    await perms.record_decision(run_id, "Edit", allow=True, by="policy", reason="in the tree")

    (decision,) = await perms.decisions("sample", ticket.id)
    assert (decision.tool, decision.decision, decision.by, decision.reason) == (
        "Edit",
        "allow",
        "policy",
        "in the tree",
    )


async def test_a_decision_for_an_unknown_run_is_not_found(perms: PermissionService) -> None:
    with pytest.raises(NotFoundError, match="no such run"):
        await perms.record_decision("nope", "Edit", allow=True, by="policy")
