"""A runner on another machine: claim, lapse, the four refusals, the log tail and the result."""

from pathlib import Path
from typing import Any

import pytest

from checks_support import REPO, Clock, FakeForge, write_config
from code_factory.checks.models import MAIN, Claim, PullHead, RunnerResult
from code_factory.checks.service import CheckService
from code_factory.platform.errors import BadRequestError, ConflictError
from code_factory.tickets.models import Ticket
from code_factory.tickets.service import ActivityService
from git_support import git

CONFIG = "[checks]\ncommand = 'true'\n[agents]\nsandbox = false\n"
MAIN_CONFIG = "[checks]\ncommand = 'true'\nmain = 'true'\n[agents]\nsandbox = false\n"
TAIL = 65_536


@pytest.fixture
def pull(forge: FakeForge, started: Ticket, root: Path) -> str:
    """The open pull request of `started`: its head."""
    write_config(root, CONFIG)
    head = git(root, "rev-parse", "ticket/cf-1")
    forge.heads.append(PullHead(repository=REPO, ticket_id=started.id, head=head))
    return head


async def claimed(checks: CheckService, runner: str = "r1") -> Claim:
    found = await checks.claim_for_runner(runner, [REPO])
    assert found is not None
    return found


def result(claim: Claim, code: int = 0, tail: str = "") -> RunnerResult:
    return RunnerResult(head=claim.head, tree_id=claim.tree_id, exit_code=code, log_tail=tail)


async def checks_records(activity: ActivityService, ticket: Ticket) -> list[dict[str, Any]]:
    page = await activity.list_activity(ticket.id, kinds=["checks"], limit=100)
    return [item.data for item in page.items]


async def test_a_runner_claims_the_head_of_an_open_pull_request_with_its_tree(
    checks: CheckService, started: Ticket, pull: str, root: Path
) -> None:
    claim = await claimed(checks)
    assert (claim.repository, claim.id, claim.head) == (REPO, started.id, pull)
    assert claim.tree_id == git(root, "rev-parse", f"{pull}^{{tree}}")
    assert await checks.left_to_runners(REPO, started.id, pull)


async def test_a_claim_holds_for_59_seconds_and_lapses_at_60(
    checks: CheckService,
    started: Ticket,
    pull: str,
    clock: Clock,
) -> None:
    await claimed(checks, "r1")
    clock.after(seconds=59)
    assert await checks.claim_for_runner("r2", [REPO]) is None
    clock.after(seconds=1)
    taken = await checks.claim_for_runner("r2", [REPO])
    assert taken is not None
    assert not await checks.beat("r1", REPO, started.id, pull)
    assert await checks.beat("r2", REPO, started.id, pull)


async def test_a_beat_keeps_the_claim_past_its_first_minute(
    checks: CheckService, started: Ticket, pull: str, clock: Clock
) -> None:
    await claimed(checks, "r1")
    clock.after(seconds=59)
    assert await checks.beat("r1", REPO, started.id, pull)
    clock.after(seconds=59)
    assert await checks.claim_for_runner("r2", [REPO]) is None


async def test_a_repository_the_board_does_not_track_is_not_claimed(
    checks: CheckService,
    pull: str,  # noqa: ARG001
) -> None:
    assert await checks.claim_for_runner("r1", ["elsewhere"]) is None


async def test_main_is_claimed_when_no_pull_request_is_open_and_no_run_of_its_tip_is_recorded(
    checks: CheckService, root: Path
) -> None:
    write_config(root, MAIN_CONFIG)
    claim = await claimed(checks)
    assert claim.id == MAIN
    assert claim.head == git(root, "rev-parse", "origin/main")


async def test_a_main_result_is_recorded_and_frees_the_claim(
    checks: CheckService, root: Path
) -> None:
    write_config(root, MAIN_CONFIG)
    claim = await claimed(checks)
    await checks.accept("r1", REPO, MAIN, claim.head, result(claim, 0, "all good\n"))
    (record,) = await checks.main_records()
    assert (record.repository, record.commit, record.exit_code) == (REPO, claim.head, 0)
    assert await checks.claim_for_runner("r2", [REPO]) is None


async def test_a_result_is_recorded_as_the_boards_own_check_of_the_ticket(
    checks: CheckService, activity: ActivityService, started: Ticket, pull: str
) -> None:
    claim = await claimed(checks)
    await checks.accept("r1", REPO, started.id, pull, result(claim, 3, "boom\n"))
    (record,) = await checks_records(activity, started)
    assert (record["commit"], record["exit_code"], record["tree_id"]) == (pull, 3, claim.tree_id)


async def test_a_runners_record_names_the_tree_as_the_boards_own_run_of_that_head_does(
    checks: CheckService, activity: ActivityService, started: Ticket, pull: str
) -> None:
    claim = await claimed(checks)
    await checks.accept("r1", REPO, started.id, pull, result(claim))
    await checks.run_now(await checks.start(started.id))
    remote, board = sorted(await checks_records(activity, started), key=lambda r: "tree_id" in r)
    assert remote["commit"] == board["commit"] == pull
    assert remote["tree"] == board["tree"]


async def test_a_result_of_another_runner_is_refused_and_leaves_the_claim_with_its_holder(
    checks: CheckService, activity: ActivityService, started: Ticket, pull: str
) -> None:
    claim = await claimed(checks, "r1")
    given = result(claim)
    with pytest.raises(ConflictError, match="is not yours: claim again"):
        await checks.accept("r2", REPO, started.id, pull, given)
    assert await checks.beat("r1", REPO, started.id, pull)
    assert await checks_records(activity, started) == []


async def test_a_result_for_a_head_that_moved_is_refused_and_gives_the_claim_up(
    checks: CheckService,
    activity: ActivityService,
    forge: FakeForge,
    started: Ticket,
    pull: str,
) -> None:
    claim = await claimed(checks)
    forge.heads[:] = [PullHead(repository=REPO, ticket_id=started.id, head="f" * 40)]
    given = result(claim)
    with pytest.raises(ConflictError, match="head moved since the claim"):
        await checks.accept("r1", REPO, started.id, pull, given)
    assert await checks_records(activity, started) == []
    assert not await checks.beat("r1", REPO, started.id, pull)
    assert not await checks.left_to_runners(REPO, started.id, pull)


async def test_a_result_naming_another_head_is_refused_and_gives_the_claim_up(
    checks: CheckService, activity: ActivityService, started: Ticket, pull: str
) -> None:
    claim = await claimed(checks)
    other = claim.model_copy(update={"head": "e" * 40})
    given = result(other)
    with pytest.raises(ConflictError, match="another head than"):
        await checks.accept("r1", REPO, started.id, pull, given)
    assert await checks_records(activity, started) == []
    assert not await checks.beat("r1", REPO, started.id, pull)


async def test_a_result_for_another_tree_is_refused_and_gives_the_claim_up(
    checks: CheckService, activity: ActivityService, started: Ticket, pull: str
) -> None:
    claim = await claimed(checks)
    wrong = RunnerResult(head=pull, tree_id="d" * 40, exit_code=0)
    assert wrong.tree_id != claim.tree_id
    with pytest.raises(ConflictError, match="not the claimed head's tree"):
        await checks.accept("r1", REPO, started.id, pull, wrong)
    assert await checks_records(activity, started) == []
    assert not await checks.beat("r1", REPO, started.id, pull)


async def test_a_log_tail_of_65536_bytes_is_taken_and_one_byte_more_is_refused(
    checks: CheckService, activity: ActivityService, started: Ticket, pull: str
) -> None:
    claim = await claimed(checks)
    big = result(claim, 0, "x" * (TAIL + 1))
    with pytest.raises(BadRequestError, match="holds over 65536 bytes"):
        await checks.accept("r1", REPO, started.id, pull, big)
    assert await checks.beat("r1", REPO, started.id, pull)
    await checks.accept("r1", REPO, started.id, pull, result(claim, 0, "x" * TAIL))
    assert len(await checks_records(activity, started)) == 1


async def test_a_gave_back_head_is_the_boards_to_check(
    checks: CheckService, started: Ticket, pull: str
) -> None:
    await claimed(checks)
    assert await checks.release("r1", REPO, started.id, pull)
    assert not await checks.left_to_runners(REPO, started.id, pull)
    assert await checks.claim_for_runner("r2", [REPO]) is None
