"""Running a check on a real repository with a real shell: rows, records, statuses, logs."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from checks_support import REPO, FakeForge, write_config
from code_factory.checks.models import PullHead, RunState, Scope, Verdict
from code_factory.checks.service import CheckService
from code_factory.tickets.models import NewActivity, NewTicket, Ticket
from code_factory.tickets.service import ActivityService, TicketService
from git_support import commit as make_commit
from git_support import git
from ticket_values import OWNER

CONTEXT = "code-factory/checks"


def plain(command: str, *extra: str) -> str:
    """A config whose checks command is `command`, run as it is."""
    lines = [f"command = '{command}'", *extra]
    return "[checks]\n" + "\n".join(lines) + "\n[agents]\nsandbox = false\n"


async def run(checks: CheckService, ticket: Ticket) -> int:
    check_id = await checks.start(ticket.id)
    await checks.run_now(check_id)
    return check_id


async def records(
    activity: ActivityService, ticket: Ticket, kind: str = "checks"
) -> list[dict[str, Any]]:
    page = await activity.list_activity(ticket.id, kinds=[kind], limit=100)
    return [item.data for item in page.items]


async def test_a_passing_command_finishes_the_row_records_the_check_and_posts_the_status(
    checks: CheckService,
    activity: ActivityService,
    forge: FakeForge,
    started: Ticket,
    root: Path,
    state: Path,
) -> None:
    write_config(root, plain("true"))
    tip = git(root, "rev-parse", "ticket/cf-1")
    forge.heads.append(PullHead(repository=REPO, ticket_id=started.id, head=tip))

    check_id = await run(checks, started)

    row = await checks.get(check_id)
    assert (row.state, row.verdict, row.exit_code) == (RunState.FINISHED, Verdict.PASSED, 0)
    (record,) = await records(activity, started)
    assert record["commit"] == tip
    assert record["exit_code"] == 0
    assert record["tree_id"] == git(root, "rev-parse", f"{tip}^{{tree}}")
    assert Path(record["log"]).parent == state.resolve() / "checks"
    assert [post[2:] for post in forge.posts] == [
        ("pending", CONTEXT, "The board's checks are running"),
        ("success", CONTEXT, "The board's checks passed"),
    ]
    assert {post[1] for post in forge.posts} == {tip}


async def test_a_failing_command_is_a_failed_row_and_a_failure_status(
    checks: CheckService,
    activity: ActivityService,
    forge: FakeForge,
    started: Ticket,
    root: Path,
) -> None:
    write_config(root, plain("echo boom; exit 3"))
    check_id = await run(checks, started)
    row = await checks.get(check_id)
    assert (row.verdict, row.exit_code) == (Verdict.FAILED, 3)
    (record,) = await records(activity, started)
    assert record["exit_code"] == 3
    assert "boom" in Path(record["log"]).read_text()
    assert forge.posts[-1][2:] == ("failure", CONTEXT, "The board's checks failed: exited 3")


async def test_sealed_files_are_checked_on_the_candidate_and_at_merge(
    checks: CheckService, started: Ticket, root: Path, state: Path
) -> None:
    path = "acceptance.t"
    source = "original contract\n"
    git(root, "checkout", started.branch)
    sealed = make_commit(root, "Write the acceptance check", **{path: source})
    candidate = make_commit(root, "Build the feature", feature="implementation\n")
    modified = make_commit(root, "Weaken the acceptance check", **{path: "changed\n"})
    git(root, "checkout", "main")
    write_config(root, plain("echo ran-command"))

    earlier = await checks.start(started.id, head=modified)
    await checks.run_now(earlier)
    assert await checks.verdict(REPO, started.id, modified) == "passed"

    receipts = state / "spec-locks"
    receipts.mkdir(parents=True)
    receipt = receipts / f"{started.id}.json"
    receipt.write_text(
        json.dumps({"commit": sealed, "files": {path: hashlib.sha256(source.encode()).hexdigest()}})
    )
    assert await checks.verdict(REPO, started.id, modified) == "failed"

    good = await checks.start(started.id, head=candidate)
    assert (await checks.run_now(good)).verdict is Verdict.PASSED
    assert await checks.verdict(REPO, started.id, candidate) == "passed"

    bad = await checks.start(started.id, head=modified)
    row = await checks.run_now(bad)
    assert row.verdict is Verdict.FAILED
    log = Path(row.log_path).read_text()
    assert f"Spec lock refused {path!r}" in log
    assert "ran-command" not in log

    digest = hashlib.sha256(source.encode()).hexdigest()
    for invalid in (
        [],
        {},
        {"commit": sealed, "files": {}},
        {"commit": sealed, "files": {"../other": digest}},
        {"commit": sealed, "files": {path: ""}},
        {"commit": "7" * 40, "files": {path: digest}},
    ):
        receipt.write_text(json.dumps(invalid))
        assert await checks.verdict(REPO, started.id, candidate) == "failed"


async def test_card_checks_keep_only_the_newest_usable_verdict_for_each_head(
    checks: CheckService, activity: ActivityService, started: Ticket, tickets: TicketService
) -> None:
    other = await tickets.create(NewTicket(repository=REPO, title="Other ticket"), by=OWNER)
    for commit, codes in (
        ("keep", (1, 0, -1, 137, "5", True, 2.5, None)),
        ("newer", (3,)),
    ):
        for code in codes:
            await activity.append(
                started.id,
                NewActivity(kind="checks", data={"commit": commit, "exit_code": code}),
                by=OWNER,
            )
    await activity.append(
        other.id, NewActivity(kind="checks", data={"commit": "other", "exit_code": 2}), by=OWNER
    )

    results = await checks.card_records({started.id: "keep", other.id: "", "CF-999": "gone"})

    assert {k: [(r.commit, r.exit_code) for r in rows] for k, rows in results.items()} == {
        started.id: [("keep", 0)],
        other.id: [("other", 2)],
    }
    assert await checks.card_records({started.id: "missing"}) == {}
    assert len((await checks.records_of([started.id]))[started.id]) == 9


@pytest.mark.parametrize(("fast", "expected"), [("true", True), ("false", False)])
async def test_review_fix_checks_cannot_supply_the_merge_verdict(
    checks: CheckService,
    forge: FakeForge,
    started: Ticket,
    root: Path,
    fast: str,
    expected: bool,
) -> None:
    write_config(root, plain("exit 3", f"fast = '{fast}'"))
    head = git(root, "rev-parse", "ticket/cf-1")
    forge.heads.append(PullHead(repository=REPO, ticket_id=started.id, head=head))

    check_id = await checks.queue_head(started.id, head, review_fix=True)
    assert check_id is not None
    assert (await checks.get(check_id)).scope is Scope.FAST
    await checks.run_now(check_id)

    assert await checks.verdict(REPO, started.id, head) == "missing"
    assert forge.posts == []
    reached = [
        row for row in await checks.recent_runs(subject=started.id) if row.scope is Scope.REACHED
    ]
    assert bool(reached) is expected
    if reached:
        await checks.run_now(reached[0].id)
        assert await checks.verdict(REPO, started.id, head) == "failed"


async def test_a_command_that_rewrites_a_tracked_file_gives_no_verdict_and_a_pending_status(
    checks: CheckService,
    activity: ActivityService,
    forge: FakeForge,
    started: Ticket,
    root: Path,
) -> None:
    write_config(root, plain("echo more >> work.txt"))
    check_id = await run(checks, started)
    row = await checks.get(check_id)
    assert (row.verdict, row.exit_code) == (Verdict.NO_VERDICT, -1)
    (record,) = await records(activity, started)
    log = Path(record["log"]).read_text()
    assert (
        "gate: the tree changed while the checks ran: no verdict on the commit it began on" in log
    )
    assert forge.posts[-1][2:] == (
        "pending",
        CONTEXT,
        "The board's checks gave no verdict and run again",
    )


async def test_a_setup_that_fails_is_no_verdict_and_says_so_in_the_log(
    checks: CheckService, activity: ActivityService, started: Ticket, root: Path
) -> None:
    write_config(root, plain("true") + '[agents]\nsetup = "exit 7"\n'.replace("[agents]\n", ""))
    check_id = await run(checks, started)
    row = await checks.get(check_id)
    assert (row.verdict, row.exit_code) == (Verdict.NO_VERDICT, -1)
    (record,) = await records(activity, started)
    log = Path(record["log"]).read_text()
    assert log.startswith("the snapshot's setup failed with exit code 7; see ")


async def test_the_snapshot_is_removed_when_the_run_ends(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, plain("pwd > " + str(root.parent / "where.txt")))
    await run(checks, started)
    where = Path((root.parent / "where.txt").read_text().strip())
    assert where.parent == (root / ".code-factory" / "worktrees").resolve()
    assert where.name.startswith("check-")
    assert not where.exists()
    assert "check-" not in git(root, "worktree", "list")


async def test_a_passed_run_leaves_its_build_folder_to_the_next_and_a_failed_one_none(
    checks: CheckService, started: Ticket, root: Path, state: Path
) -> None:
    (root / ".git" / "info" / "exclude").write_text("target/\n")  # build output is ignored
    write_config(root, plain("mkdir -p target/linux && echo built > target/linux/artifact"))
    await run(checks, started)
    cache = state / "check-cache" / started.id / "linux-target"
    assert (cache / "artifact").read_text() == "built\n"

    write_config(root, plain("cat target/linux/artifact; exit 4"))
    await run(checks, started)
    assert (cache / "artifact").exists() is False


@pytest.mark.parametrize("command", ["kill -9 $$"])
async def test_two_system_kills_end_with_both_named_in_the_final_record(
    checks: CheckService, activity: ActivityService, started: Ticket, root: Path, command: str
) -> None:
    write_config(root, plain(command))
    await run(checks, started)
    first, final = await records(activity, started)
    assert first["outcome"] == "killed"
    assert first["exit_code"] == -9
    assert "outcome" not in final
    assert [kill["exit_code"] for kill in final["kills"]] == [-9, -9]
    assert final["log"] != first["log"]


async def test_a_kill_then_a_clean_run_records_the_kill_and_passes(
    checks: CheckService, activity: ActivityService, started: Ticket, root: Path, tmp_path: Path
) -> None:
    marker = tmp_path / "marker"
    write_config(
        root, plain(f"if [ -e {marker} ]; then exit 0; else touch {marker}; kill -9 $$; fi")
    )
    check_id = await run(checks, started)
    first, final = await records(activity, started)
    assert first["outcome"] == "killed"
    assert final["exit_code"] == 0
    assert "kills" not in final
    assert (await checks.get(check_id)).verdict is Verdict.PASSED


async def test_a_setup_that_rewrites_a_tracked_file_is_no_verdict_and_the_command_never_runs(
    checks: CheckService, activity: ActivityService, started: Ticket, root: Path
) -> None:
    ran = root.parent / "ran.txt"
    write_config(root, plain(f"touch {ran}") + 'setup = "echo more >> work.txt"\n')
    check_id = await run(checks, started)
    row = await checks.get(check_id)
    assert (row.verdict, row.exit_code) == (Verdict.NO_VERDICT, -1)
    (record,) = await records(activity, started)
    assert (
        "gate: the snapshot's setup changed tracked files: no verdict"
        in Path(record["log"]).read_text()
    )
    assert not ran.exists()


async def test_a_setup_that_adds_an_untracked_file_leaves_the_verdict_to_the_command(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, plain("true") + 'setup = "echo more > made-by-setup.txt"\n')
    row = await checks.get(await run(checks, started))
    assert row.verdict == Verdict.PASSED


async def test_a_passing_fast_run_says_nothing_to_the_merge_gate(
    checks: CheckService, activity: ActivityService, started: Ticket, root: Path
) -> None:
    write_config(root, plain("exit 3", 'fast = "true"'))
    check_id = await checks.start(started.id, scope=Scope.FAST)
    await checks.run_now(check_id)
    (record,) = await records(activity, started)
    assert record["scope"] == "fast"
    head = git(root, "rev-parse", "ticket/cf-1")
    assert await checks.verdict(REPO, started.id, head) == "missing"
