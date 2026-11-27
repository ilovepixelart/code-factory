"""`[release] verify`: hourly runs of the newest release, one bug per release, never two at once."""

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from checks_support import REPO, Clock, write_config
from code_factory.checks.service import CheckService
from code_factory.platform.errors import ConflictError
from code_factory.releases.service import ReleaseService
from code_factory.tickets.models import TicketFilter
from code_factory.tickets.service import TicketService
from git_support import git

OWNER = "alex"
HOUR = timedelta(hours=1)


@pytest.fixture
async def released(releases: ReleaseService, root: Path) -> str:
    """Release 0.1.0 of `sample`, tagged at the clock's time."""
    await releases.draft(REPO, "0.1.0", by=OWNER)
    await releases.publish(REPO, "0.1.0", by=OWNER)
    await releases.record_tag_commit(
        REPO, "0.1.0", git(root, "rev-parse", "main").strip(), by=OWNER
    )
    await releases.record_tagged(REPO, "0.1.0", by=OWNER)
    return "0.1.0"


def verifying(root: Path, command: str) -> None:
    write_config(root, f"[checks]\ncommand = 'true'\n[release]\nverify = '{command}'\n")


async def bugs(tickets: TicketService) -> list[str]:
    found = await tickets.list(TicketFilter(repository=REPO))
    return sorted(ticket.id for ticket in found if ticket.type == "bug")


async def test_a_passing_verification_is_recorded_and_files_no_bug(
    checks: CheckService, released: str, root: Path, tickets: TicketService
) -> None:
    verifying(root, "true")
    release = await checks.newest_release(REPO)
    assert release is not None
    record = await checks.verify(REPO, release)
    assert (record.release, record.exit_code, record.ticket) == (released, 0, "")
    assert await bugs(tickets) == []
    with pytest.raises(ConflictError, match="no longer due"):
        await checks.verify(REPO, release, scheduled=True)
    assert await checks.verify_records(REPO) == [record]


@pytest.mark.usefixtures("released")
async def test_a_failing_verification_files_one_bug_for_the_release_however_often_it_fails(
    checks: CheckService, root: Path, tickets: TicketService, clock: Clock
) -> None:
    verifying(root, "echo broken; exit 3")
    release = await checks.newest_release(REPO)
    assert release is not None
    first = await checks.verify(REPO, release)
    clock.after(hours=1)
    second = await checks.verify(REPO, release)
    assert first.exit_code == 3
    assert first.ticket != ""
    assert second.ticket == first.ticket
    assert await bugs(tickets) == [first.ticket]


@pytest.mark.usefixtures("released")
async def test_a_verification_still_running_makes_the_next_pass_start_none_until_it_ends(
    checks: CheckService, root: Path, tickets: TicketService, clock: Clock
) -> None:
    gate = root.parent / "gate"
    verifying(root, f"while [ ! -e {gate} ]; do sleep 0.05; done; exit 4")
    release = await checks.due_verify(REPO)
    assert release is not None
    running = asyncio.create_task(checks.verify(REPO, release))
    await asyncio.sleep(0.5)
    clock.after(hours=2)
    assert await checks.due_verify(REPO) is None
    gate.write_text("go")
    record = await asyncio.wait_for(running, timeout=20)
    assert record.exit_code == 4
    clock.after(hours=2)
    assert await checks.due_verify(REPO) is not None
    assert await bugs(tickets) == [record.ticket]
