"""A ticket check of the composed app: the real srt, with the settings the app builds."""

from pathlib import Path

import pytest

from app_lifespan import IDLE_MODULES
from checks_support import write_config
from code_factory.app import build_services
from code_factory.checks.models import Verdict
from code_factory.checks.service import CheckService
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine
from code_factory.platform.module import Resources
from code_factory.tickets.models import Ticket
from code_factory.tickets.service import ActivityService


@pytest.fixture
def composed(settings: Settings, uow: UnitOfWork, state: Path) -> CheckService:
    """The check service as `app.py` wires it, its state in the test's folder."""
    own = settings.model_copy(update={"state_dir": state})
    resources = Resources(own, create_engine(own), uow, BackgroundTasks())
    return build_services(resources, IDLE_MODULES).get(CheckService)


async def test_a_ticket_check_runs_inside_srt_and_records_its_verdict(
    composed: CheckService,
    activity: ActivityService,
    started: Ticket,
    tracked: Path,
) -> None:
    command = 'echo inside > "$CLAUDE_CODE_TMPDIR/made" && cat "$CLAUDE_CODE_TMPDIR/made"'
    write_config(tracked, f"[checks]\ncommand = '{command}'\n")
    row = await composed.run_now(await composed.start(started.id))

    assert row.verdict is Verdict.PASSED, Path(row.log_path).read_text()
    page = await activity.list_activity(started.id, kinds=["checks"], limit=10)
    [record] = [item.data for item in page.items]
    assert record["exit_code"] == 0
    assert Path(record["log"]).read_text().splitlines()[0] == "inside"


async def test_a_ticket_check_cannot_write_outside_its_tree(
    composed: CheckService, started: Ticket, tracked: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    write_config(tracked, f"[checks]\ncommand = 'echo escaped > {outside}'\n")
    row = await composed.run_now(await composed.start(started.id))

    log = Path(row.log_path).read_text()
    assert (row.verdict, row.exit_code) == (Verdict.FAILED, 1), log
    assert not outside.exists()
    assert "Operation not permitted" in log or "Read-only file system" in log


# A test run writes caches into its tree (Python's __pycache__, a build folder); those files are
# not the commit's, so they must not cost the commit its verdict.
async def test_a_check_that_leaves_a_new_untracked_file_keeps_its_verdict(
    composed: CheckService, started: Ticket, tracked: Path
) -> None:
    write_config(
        tracked, "[checks]\ncommand = 'mkdir -p __pycache__ && echo x > __pycache__/c.pyc'\n"
    )
    row = await composed.run_now(await composed.start(started.id))

    assert row.verdict is Verdict.PASSED, Path(row.log_path).read_text()


async def test_a_check_that_changes_a_tracked_file_gives_no_verdict(
    composed: CheckService, started: Ticket, tracked: Path
) -> None:
    write_config(tracked, "[checks]\ncommand = 'echo changed >> readme.md'\n")
    row = await composed.run_now(await composed.start(started.id))

    assert row.verdict is not Verdict.PASSED
    assert row.exit_code == -1
