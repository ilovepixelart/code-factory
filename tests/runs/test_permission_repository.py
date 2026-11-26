from typing import Literal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.runs.models import Decision, PermissionRequest, Review
from code_factory.runs.repository import PermissionRepository
from runs_values import at


def request(
    request_id: str = "aaaaaaaaaaaa", *, kind: str | None = "Bash(git *)", n: int = 0
) -> PermissionRequest:
    return PermissionRequest(
        id=request_id,
        repository="sample",
        ticket_key="CF-1",
        tool="Bash",
        summary="git status",
        kind=kind,
        requested_at=at(n),
    )


@pytest.fixture
def perms(db_session: AsyncSession) -> PermissionRepository:
    return PermissionRepository(db_session)


async def test_a_request_is_read_back_pending(perms: PermissionRepository) -> None:
    await perms.add_request(request())
    found = await perms.get_request("aaaaaaaaaaaa")
    assert found == request()
    assert found.status == "pending"


async def test_pending_requests_are_oldest_first(perms: PermissionRepository) -> None:
    await perms.add_request(request("bbbbbbbbbbbb", n=2))
    await perms.add_request(request("aaaaaaaaaaaa", n=1))
    assert [r.id for r in await perms.pending()] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]


async def test_an_answer_is_won_once(perms: PermissionRepository) -> None:
    await perms.add_request(request())
    assert await perms.answer("aaaaaaaaaaaa", "allow", "owner", at(5)) is True
    assert await perms.answer("aaaaaaaaaaaa", "deny", "owner", at(6)) is False
    found = await perms.get_request("aaaaaaaaaaaa")
    assert found is not None
    assert (found.status, found.verdict, found.answered_at) == ("answered", "allow", at(5))
    assert await perms.pending() == []


async def test_a_request_older_than_a_moment_expires_and_is_no_longer_pending(
    perms: PermissionRepository,
) -> None:
    await perms.add_request(request("aaaaaaaaaaaa", n=0))
    await perms.add_request(request("bbbbbbbbbbbb", n=10))
    expired = await perms.expire_before(at(10))
    assert [r.id for r in expired] == ["aaaaaaaaaaaa"]
    assert [r.id for r in await perms.pending()] == ["bbbbbbbbbbbb"]
    assert await perms.answer("aaaaaaaaaaaa", "allow", "owner", at(11)) is False


async def test_a_pending_request_is_withdrawn_but_an_answered_one_is_not(
    perms: PermissionRepository,
) -> None:
    await perms.add_request(request("aaaaaaaaaaaa"))
    await perms.add_request(request("bbbbbbbbbbbb"))
    await perms.answer("bbbbbbbbbbbb", "allow", "owner", at(1))
    assert await perms.withdraw("aaaaaaaaaaaa") is True
    assert await perms.withdraw("bbbbbbbbbbbb") is False
    found = await perms.get_request("aaaaaaaaaaaa")
    assert found is not None
    assert found.status == "withdrawn"


async def test_the_pending_requests_made_before_a_restart_are_withdrawn(
    perms: PermissionRepository,
) -> None:
    await perms.add_request(request("aaaaaaaaaaaa", n=-10))
    await perms.add_request(request("bbbbbbbbbbbb", n=-10))
    await perms.add_request(request("cccccccccccc", n=-1))
    await perms.answer("bbbbbbbbbbbb", "allow", "owner", at(-5))
    assert await perms.withdraw_pending_before(at(0)) == 2
    assert await perms.pending() == []


async def test_a_request_made_at_or_after_the_restart_is_not_withdrawn(
    perms: PermissionRepository,
) -> None:
    await perms.add_request(request("aaaaaaaaaaaa", n=0))
    await perms.add_request(request("bbbbbbbbbbbb", n=3))
    assert await perms.withdraw_pending_before(at(0)) == 0
    assert [r.id for r in await perms.pending()] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]


async def test_the_answered_history_lists_each_answer_by_kind(perms: PermissionRepository) -> None:
    await perms.add_request(request("aaaaaaaaaaaa", kind="Bash(git *)"))
    await perms.add_request(request("bbbbbbbbbbbb", kind="Bash(git *)"))
    await perms.add_request(request("cccccccccccc", kind=None))
    await perms.add_request(request("dddddddddddd", kind="Edit"))
    for request_id, verdict in [
        ("aaaaaaaaaaaa", "allow"),
        ("bbbbbbbbbbbb", "deny"),
        ("cccccccccccc", "allow"),
    ]:
        await perms.answer(request_id, verdict, "owner", at(1))
    assert sorted(await perms.answered_history()) == [("Bash(git *)", False), ("Bash(git *)", True)]


async def test_a_rule_is_adopted_once_and_listed_in_the_order_adopted(
    perms: PermissionRepository,
) -> None:
    assert await perms.adopt_rule("Edit", at(1)) is True
    assert await perms.adopt_rule("Bash(git *)", at(2)) is True
    assert await perms.adopt_rule("Edit", at(3)) is False
    assert await perms.rules() == ["Edit", "Bash(git *)"]


def decision(
    by: Literal["policy", "reviewer", "owner"],
    verdict: Literal["allow", "deny"],
    n: int,
    ticket: str = "CF-1",
) -> Decision:
    return Decision(
        at=at(n),
        repository="sample",
        ticket_key=ticket,
        tool="Read",
        decision=verdict,
        by=by,
    )


async def test_the_latest_decisions_of_a_ticket_come_oldest_first(
    perms: PermissionRepository,
) -> None:
    await perms.add_decision(decision("policy", "deny", 0))
    await perms.add_decision(decision("owner", "allow", 1))
    await perms.add_decision(decision("policy", "deny", 2))
    await perms.add_decision(decision("policy", "deny", 9, ticket="CF-2"))
    latest = await perms.latest_decisions("sample", "CF-1", 2)
    assert [(d.by, d.decision) for d in latest] == [("owner", "allow"), ("policy", "deny")]


async def test_decisions_older_than_a_moment_are_pruned(perms: PermissionRepository) -> None:
    await perms.add_decision(decision("owner", "allow", 0))
    await perms.add_decision(decision("owner", "allow", 5))
    await perms.add_decision(decision("owner", "allow", 10))
    assert await perms.prune_decisions(at(5)) == 1
    assert len(await perms.latest_decisions("sample", "CF-1", 10)) == 2


async def test_reviews_are_tallied_per_session(perms: PermissionRepository) -> None:
    def review(session: str, verdict: Literal["allow", "deny", "owner"], n: int) -> Review:
        return Review(
            at=at(n),
            session_id=session,
            ticket_key="CF-1",
            tool="Bash",
            summary="ls",
            input_sha256="ab" * 32,
            verdict=verdict,
        )

    assert await perms.record_review(review("s1", "allow", 0)) == 1
    assert await perms.record_review(review("s1", "deny", 1)) == 2
    assert await perms.record_review(review("s2", "owner", 2)) == 1
    assert await perms.review_count("s1") == 2
