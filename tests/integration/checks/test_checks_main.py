"""Runs of `[checks] main` on the default branch: when one is due, its record, the merge search."""

from pathlib import Path

import pytest

from checks_support import REPO, Clock, write_config
from code_factory.checks.service import CheckService
from code_factory.platform.errors import BadRequestError, ConflictError
from code_factory.tickets.models import Ticket
from git_support import commit, git

MAIN_ONLY = "[checks]\nmain = 'test ! -e broken.txt'\n[agents]\nsandbox = false\n"


def merge_feature(root: Path, name: str, **files: str) -> str:
    """A `--no-ff` merge of a branch with one commit into main, pushed; the merge commit."""
    git(root, "checkout", "-q", "-b", name)
    commit(root, f"Work of {name}", **files)
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", f"Merge branch '{name}'", name)
    git(root, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    return git(root, "rev-parse", "HEAD")


async def test_no_run_is_due_without_a_main_command(checks: CheckService, root: Path) -> None:
    write_config(root, "[checks]\ncommand = 'true'\n")
    assert await checks.due_main(REPO) is None


async def test_a_run_is_due_on_the_tip_until_one_is_recorded_and_again_on_a_new_tip(
    checks: CheckService, root: Path
) -> None:
    write_config(root, MAIN_ONLY)
    tip = git(root, "rev-parse", "origin/main")
    assert await checks.due_main(REPO) == tip
    await checks.run_now(await checks.start_main(REPO))
    assert await checks.due_main(REPO) is None
    moved = merge_feature(root, "more", **{"more.txt": "x\n"})
    assert await checks.due_main(REPO) == moved


async def test_no_run_of_main_is_due_while_a_ticket_check_is_queued(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, "[checks]\ncommand = 'true'\nmain = 'true'\n[agents]\nsandbox = false\n")
    assert await checks.due_main(REPO) is not None
    await checks.start(started.id)
    assert await checks.due_main(REPO) is None


async def test_a_run_of_main_is_recorded_and_a_second_one_queued_is_refused(
    checks: CheckService, root: Path
) -> None:
    write_config(root, MAIN_ONLY)
    check_id = await checks.start_main(REPO)
    with pytest.raises(ConflictError, match="main's run is already queued"):
        await checks.start_main(REPO)
    await checks.run_now(check_id)
    (record,) = await checks.main_records()
    assert (record.repository, record.commit, record.exit_code, record.passed) == (
        REPO,
        git(root, "rev-parse", "origin/main"),
        0,
        git(root, "rev-parse", "origin/main"),
    )


async def test_a_main_run_without_the_main_command_is_refused_naming_the_key(
    checks: CheckService, root: Path
) -> None:
    write_config(root, "[checks]\ncommand = 'true'\n")
    with pytest.raises(BadRequestError, match=r"no \[checks\] main command"):
        await checks.start_main(REPO)


async def test_a_failing_main_blames_the_first_merge_whose_tree_fails(
    checks: CheckService, root: Path
) -> None:
    write_config(root, MAIN_ONLY)
    await checks.run_now(await checks.start_main(REPO))
    first = merge_feature(root, "alpha", **{"alpha.txt": "a\n"})
    breaking = merge_feature(root, "beta", **{"broken.txt": "b\n"})
    last = merge_feature(root, "gamma", **{"gamma.txt": "c\n"})
    assert len({first, breaking, last}) == 3
    await checks.run_now(await checks.start_main(REPO))
    (record,) = await checks.main_records()
    assert (record.commit, record.exit_code != 0) == (last, True)
    assert (record.broken_by, record.searched) == (breaking, True)
    assert record.passed != last


async def test_main_is_left_to_a_runner_that_offered_until_its_offer_is_600_seconds_old(
    checks: CheckService, root: Path, clock: Clock
) -> None:
    write_config(root, MAIN_ONLY)
    assert await checks.claim_for_runner("r1", [REPO]) is not None
    assert await checks.due_main(REPO) is None
    clock.after(seconds=599)
    assert await checks.due_main(REPO) is None
    clock.after(seconds=1)
    assert await checks.due_main(REPO) == git(root, "rev-parse", "origin/main")
