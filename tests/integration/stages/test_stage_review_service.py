"""What an ended review run decides and what holds a merge for a review.

The diffs are read from a real temporary git repository. Sentences are the previous
implementation's (`Review before merge: ...`).
"""

from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from code_factory.checks.service import CheckService
from code_factory.platform.errors import ConflictError, UnavailableError
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs.service.flow import FlowAdapter
from code_factory.stages.service import StageService
from code_factory.tickets.models import (
    Finding,
    NewActivity,
    NewTicket,
    PullRequest,
    PullRequestState,
    Review,
    Ticket,
)
from code_factory.tickets.service import ActivityService, ReviewService, TicketService
from stage_fakes import FakeFacts
from stage_git import clone_with_origin, commit, git
from stage_values import NOW
from ticket_values import OWNER

RUN = "run-review"
PASS = Review(verdict="pass", summary="Fine.")
BLOCKER = Finding(severity="blocker", text="drops the lock", path="src/a.py", line=3)
CHANGES = Review(verdict="changes", summary="One gap.", findings=[BLOCKER])


def configure(root: Path, text: str) -> None:
    (root / ".code-factory").mkdir(exist_ok=True)
    (root / ".code-factory" / "config.toml").write_text(text)


async def test_a_review_with_no_submission_cannot_be_applied(
    stages: StageService, started: Ticket
) -> None:
    with pytest.raises(ConflictError, match="has no review submitted by run run-review"):
        await stages.apply_review(started.id, RUN, "h1")


async def test_a_run_that_submitted_no_review_cannot_borrow_an_earlier_one(
    stages: StageService, reviews: ReviewService, started: Ticket
) -> None:
    await reviews.submit_review(started.id, PASS, by="run:first")

    with pytest.raises(ConflictError, match="has no review submitted by run second"):
        await stages.apply_review(started.id, "second", "h2")

    assert await stages.review_verdicts(started.id) == []


async def test_the_actor_name_of_a_run_is_its_run_id_with_the_run_prefix(
    stages: StageService, reviews: ReviewService, started: Ticket
) -> None:
    await reviews.submit_review(started.id, PASS, by="run:abc")

    outcome = await stages.apply_review(started.id, "abc", "h1")

    assert outcome.decision == "pass"


async def test_applying_the_same_run_and_head_again_changes_nothing(
    stages: StageService, reviews: ReviewService, started: Ticket
) -> None:
    await reviews.submit_review(started.id, CHANGES, by=RUN)

    first = await stages.apply_review(started.id, RUN, "h1")
    again = await stages.apply_review(started.id, RUN, "h1")

    assert (first.decision, first.returned) == ("changes", 1)
    assert (again.decision, again.returned) == ("changes", 1)
    assert [v.outcome for v in await stages.review_verdicts(started.id)] == ["returned"]


async def test_a_retry_of_an_applied_run_answers_as_it_did_after_a_later_run_applied(
    stages: StageService, reviews: ReviewService, started: Ticket
) -> None:
    await reviews.submit_review(started.id, CHANGES, by="run:first")
    await stages.apply_review(started.id, "first", "h1")
    await reviews.submit_review(started.id, CHANGES, by="run:second")
    await stages.apply_review(started.id, "second", "h2")

    again = await stages.apply_review(started.id, "first", "h1")

    assert (again.decision, again.returned) == ("changes", 1)
    assert [v.head for v in await stages.review_verdicts(started.id)] == ["h1", "h2"]


async def test_a_review_is_not_applied_while_the_ticket_git_facts_are_unknown(
    stages: StageService, reviews: ReviewService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()
    facts.answers.clear()
    await stages.observe()
    await reviews.submit_review(started.id, CHANGES, by=RUN)

    with pytest.raises(UnavailableError, match="are unknown"):
        await stages.apply_review(started.id, RUN, "h1")

    assert await stages.review_verdicts(started.id) == []
    assert (await stages.assess(started.id)).declared == ""


async def test_a_passing_review_records_a_pass_on_the_head_and_moves_nothing(
    stages: StageService, reviews: ReviewService, started: Ticket
) -> None:
    await reviews.submit_review(started.id, PASS, by=RUN)

    outcome = await stages.apply_review(started.id, RUN, "h1")

    assert (outcome.decision, outcome.returned, outcome.sentence) == ("pass", 0, "")
    verdicts = await stages.review_verdicts(started.id)
    assert [(v.outcome, v.head, v.run_id) for v in verdicts] == [("passed", "h1", RUN)]
    assert (await stages.assess(started.id)).declared == ""


async def test_a_review_that_asks_for_changes_returns_the_ticket_to_build(
    stages: StageService, reviews: ReviewService, activity: ActivityService, started: Ticket
) -> None:
    await stages.move(started.id, "spec", OWNER)
    await reviews.submit_review(started.id, CHANGES, by=RUN)

    outcome = await stages.apply_review(started.id, RUN, "h1")

    assert (outcome.decision, outcome.returned) == ("changes", 1)
    assert [v.outcome for v in await stages.review_verdicts(started.id)] == ["returned"]
    found = await stages.assess(started.id)
    assert (found.declared, found.stage) == ("build", "build")
    last = (await activity.list_activity(started.id, kinds=["stage"], newest_first=True)).items[0]
    assert last.data == {"from": "spec", "to": "build"}


async def _in_review(tickets: TicketService, started: Ticket) -> None:
    pull = PullRequest(number=4, state=PullRequestState.OPEN, url="https://github.com/o/r/pull/4")
    await tickets.set_pull_request(started.id, pull, by=OWNER)


def _flow(stages: StageService) -> tuple[FlowAdapter, AsyncMock]:
    services = Services()
    services.add(StageService, stages)
    queue = AsyncMock()
    services.add(CheckService, Mock(spec=CheckService, queue_head=queue))
    return FlowAdapter(services), queue


async def test_a_returned_ticket_whose_fix_committed_goes_back_to_review(
    stages: StageService, reviews: ReviewService, tickets: TicketService, started: Ticket
) -> None:
    await _in_review(tickets, started)
    await reviews.submit_review(started.id, CHANGES, by=RUN)
    await stages.apply_review(started.id, RUN, "h1")
    await stages.record_review_skipped(started.id, "h2", "small", "safe change")
    assert await stages.repair_requests([started.id]) == {started.id: [NOW.timestamp()]}
    flow, queue = _flow(stages)

    await flow.build_ended(started.id, "h2")

    queue.assert_awaited_once_with(started.id, "h2", review_fix=True)
    found = await stages.assess(started.id)
    assert (found.declared, found.stage) == ("", "review")


async def test_a_ticket_the_owner_pinned_to_build_keeps_its_pin_after_a_commit(
    stages: StageService, tickets: TicketService, started: Ticket
) -> None:
    await _in_review(tickets, started)
    await stages.declare(started.id, "build", OWNER)
    flow, queue = _flow(stages)

    await flow.build_ended(started.id, "h2")

    queue.assert_awaited_once_with(started.id, "h2", review_fix=False)
    assert (await stages.assess(started.id)).declared == "build"


@pytest.mark.parametrize("pin", ["spec", "build"])
async def test_a_pin_set_after_the_review_returned_the_ticket_is_kept(
    stages: StageService, reviews: ReviewService, tickets: TicketService, started: Ticket, pin: str
) -> None:
    await _in_review(tickets, started)
    await reviews.submit_review(started.id, CHANGES, by=RUN)
    await stages.apply_review(started.id, RUN, "h1")
    returned_at = await stages.review_return_at(started.id)
    assert returned_at == NOW
    await stages.declare(started.id, pin, OWNER)
    assert await stages.review_return_at(started.id) is None

    await stages.fix_committed(started.id, returned_at=returned_at)

    assert (await stages.assess(started.id)).declared == pin


async def test_the_review_stops_returning_the_ticket_at_its_round_cap_and_tells_the_owner(
    stages: StageService, reviews: ReviewService, started: Ticket, checkout: Path
) -> None:
    configure(checkout, "[agents]\nreview_rounds = 1\n")
    await reviews.submit_review(started.id, CHANGES, by=RUN)
    await stages.apply_review(started.id, RUN, "h1")

    outcome = await stages.apply_review(started.id, RUN, "h2")

    assert outcome.decision == "halt"
    assert outcome.sentence == (
        "the review returned it 1 times ([agents] review_rounds = 1): "
        "the owner decides whether it goes round again"
    )
    assert [v.head for v in await stages.review_verdicts(started.id)] == ["h1"]


async def test_one_below_the_cap_the_review_still_returns_the_ticket(
    stages: StageService, reviews: ReviewService, started: Ticket, checkout: Path
) -> None:
    configure(checkout, "[agents]\nreview_rounds = 2\n")
    await reviews.submit_review(started.id, CHANGES, by=RUN)
    await stages.apply_review(started.id, RUN, "h1")

    assert (await stages.apply_review(started.id, RUN, "h2")).decision == "changes"
    assert (await stages.apply_review(started.id, RUN, "h3")).decision == "halt"


async def test_a_skipped_review_is_recorded_with_its_reason_and_note(
    stages: StageService, started: Ticket
) -> None:
    await stages.record_review_skipped(started.id, "h1", "budget", "the monthly budget is spent")

    [skipped] = await stages.review_verdicts(started.id)

    assert (skipped.outcome, skipped.head, skipped.reason, skipped.note) == (
        "skipped",
        "h1",
        "budget",
        "the monthly budget is spent",
    )


@pytest.fixture
async def work(tmp_path: Path, repositories: RepositoryService) -> Path:
    """A tracked repository `work` with an origin and `main` pushed."""
    root = clone_with_origin(tmp_path)
    # The config is the checkout's own file, not part of the diffs the tests make.
    (root / ".git" / "info" / "exclude").write_text(".code-factory/\n")
    await repositories.track(root)
    configure(root, "[agents]\nreview = true\n")
    return root


@pytest.fixture
async def branch(tickets: TicketService, work: Path) -> Ticket:
    """A ticket of `work` on a branch with one commit."""
    made = await tickets.create(NewTicket(repository="work", title="Work"), by=OWNER)
    git(work, "checkout", "-b", "feat/CF-9")
    commit(work, "the work", "src/a.py")
    return await tickets.set_branch(made.id, "feat/CF-9", by=OWNER)


def head(work: Path) -> str:
    return git(work, "rev-parse", "HEAD")


async def test_no_review_asked_holds_nothing(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "[agents]\nreview = false\n")

    assert await stages.review_hold(branch.id, head(work), [], review_active=False) is None


async def test_a_head_that_became_ready_a_moment_ago_waits_for_its_review_without_the_owner(
    stages: StageService, activity: ActivityService, branch: Ticket, work: Path
) -> None:
    tip = head(work)
    await activity.append(
        branch.id, NewActivity(kind="checks", data={"commit": tip}, at=NOW), by="b"
    )

    hold = await stages.review_hold(
        branch.id, tip, [], review_active=False, now=NOW + timedelta(seconds=10)
    )

    assert hold is not None
    assert (hold.reason, hold.owner) == (
        f"Review before merge: waits for the review of {tip[:7]}",
        False,
    )


async def test_a_head_no_record_dates_has_waited_past_the_run_timeout(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    tip = head(work)

    hold = await stages.review_hold(branch.id, tip, [], review_active=False)

    assert hold is not None
    assert hold.reason == f"Review before merge: no review of {tip[:7]} ended within 3600 s"
    assert hold.owner


async def test_a_pass_of_the_same_code_lets_the_merge_through_and_a_changed_file_does_not(
    stages: StageService, reviews: ReviewService, branch: Ticket, work: Path
) -> None:
    reviewed = head(work)
    await reviews.submit_review(branch.id, PASS, by=RUN)
    await stages.apply_review(branch.id, RUN, reviewed)
    quiet = commit(work, "no file changes")
    assert await stages.review_hold(branch.id, reviewed, [], review_active=False) is None
    assert await stages.review_hold(branch.id, quiet, [], review_active=False) is None

    changed = commit(work, "a file", "src/b.py")

    hold = await stages.review_hold(branch.id, changed, [], review_active=False)
    assert hold is not None
    assert hold.reason.startswith("Review before merge: no review of")


async def test_a_merge_between_the_reviewed_head_and_the_head_is_not_the_same_code(
    stages: StageService, reviews: ReviewService, branch: Ticket, work: Path
) -> None:
    reviewed = head(work)
    await reviews.submit_review(branch.id, PASS, by=RUN)
    await stages.apply_review(branch.id, RUN, reviewed)
    git(work, "checkout", "-b", "side", "main")
    commit(work, "side", "side.txt")
    git(work, "checkout", "feat/CF-9")
    git(work, "merge", "--no-ff", "-s", "ours", "-m", "keep our tree", "side")

    hold = await stages.review_hold(branch.id, head(work), [], review_active=False)

    assert hold is not None


async def test_a_blocking_finding_holds_a_passed_head_on_the_owner_with_the_findings(
    stages: StageService, reviews: ReviewService, branch: Ticket, work: Path
) -> None:
    tip = head(work)
    await reviews.submit_review(branch.id, PASS, by=RUN)
    await stages.apply_review(branch.id, RUN, tip)
    await reviews.submit_review(branch.id, CHANGES, by="run-two")

    hold = await stages.review_hold(branch.id, tip, [], review_active=False)

    assert hold is not None
    assert (hold.reason, hold.owner) == (
        "Review before merge: F1 [blocker] drops the lock",
        True,
    )


async def test_a_review_run_of_the_same_code_that_ended_without_a_pass_waits_on_the_owner(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    tip = head(work)
    ended = commit(work, "no file changes")

    hold = await stages.review_hold(branch.id, ended, [tip], review_active=False)

    assert hold is not None
    assert hold.reason == f"Review before merge: the review of {ended[:7]} ended without a pass"
    assert hold.owner


async def test_a_run_of_other_code_that_ended_does_not_count(
    stages: StageService, branch: Ticket, work: Path, activity: ActivityService
) -> None:
    earlier = head(work)
    tip = commit(work, "a file", "src/b.py")
    await activity.append(
        branch.id, NewActivity(kind="checks", data={"commit": tip}, at=NOW), by="b"
    )

    hold = await stages.review_hold(
        branch.id, tip, [earlier], review_active=False, now=NOW + timedelta(seconds=5)
    )

    assert hold is not None
    assert not hold.owner


async def test_a_skipped_review_of_the_head_holds_with_its_note(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    tip = head(work)
    await stages.record_review_skipped(branch.id, tip, "budget", "the budget is spent")

    hold = await stages.review_hold(branch.id, tip, [], review_active=False)

    assert hold is not None
    assert (
        hold.reason
        == f"Review before merge: the review of {tip[:7]} was skipped (the budget is spent)"
    )


async def test_a_small_plain_diff_within_the_bound_merges_without_a_review(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "[agents]\nreview = true\n[merge]\nunreviewed_lines = 400\n")

    assert await stages.review_hold(branch.id, head(work), [], review_active=False) is None


async def test_a_diff_over_the_bound_or_on_a_sensitive_path_still_waits_for_a_review(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "[agents]\nreview = true\n[merge]\nunreviewed_lines = 1\n")
    large = commit(work, "two more lines", "src/b.py", "src/c.py")
    assert await stages.review_hold(branch.id, large, [], review_active=False) is not None

    configure(
        work,
        '[agents]\nreview = true\n[merge]\nunreviewed_lines = 400\nsensitive = ["scripts/**"]\n',
    )
    sensitive = commit(work, "a script", "scripts/run.sh")
    assert await stages.review_hold(branch.id, sensitive, [], review_active=False) is not None


async def test_a_diff_with_a_mode_change_is_not_plain_so_it_still_waits_for_a_review(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "[agents]\nreview = true\n[merge]\nunreviewed_lines = 400\n")
    (work / "README.md").chmod(0o755)
    git(work, "add", "--all")
    git(work, "commit", "-m", "executable")

    assert await stages.review_hold(branch.id, head(work), [], review_active=False) is not None


async def test_a_diff_git_cannot_read_is_not_small(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "[agents]\nreview = true\n[merge]\nunreviewed_lines = 400\n")

    hold = await stages.review_hold(branch.id, "f" * 40, [], review_active=False)

    assert hold is not None


async def test_no_change_rule_holds_nothing(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    assert await stages.change_hold(branch.id, head(work)) is None


async def test_a_change_past_large_change_is_the_owners(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "[agents]\nlarge_change = 1\n")
    tip = commit(work, "more", "src/b.py")

    assert await stages.change_hold(branch.id, tip) == (
        "Large change: 2 changed lines, over large_change 1"
    )


async def test_a_sensitive_path_is_the_owners_whatever_its_size(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, '[agents]\nsensitive_paths = ["scripts/**"]\n')
    tip = commit(work, "a script", "scripts/run.sh")

    assert await stages.change_hold(branch.id, tip) == (
        "Sensitive path: scripts/run.sh matches scripts/**"
    )


async def test_a_change_whose_diff_cannot_be_read_holds(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "[agents]\nlarge_change = 10\n")

    assert await stages.change_hold(branch.id, "f" * 40) == (
        "Sensitive change: its settings or its diff cannot be read"
    )


async def test_a_change_with_a_mode_change_has_no_countable_size(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "[agents]\nlarge_change = 100\n")
    (work / "README.md").chmod(0o755)
    git(work, "add", "--all")
    git(work, "commit", "-m", "executable")

    assert await stages.change_hold(branch.id, head(work)) == (
        "Large change: its size cannot be counted, against large_change 100"
    )


async def test_a_config_that_cannot_be_read_holds_the_merge_for_the_owner(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "[agents\nreview = true\n")

    hold = await stages.review_hold(branch.id, head(work), [], review_active=False)

    assert hold is not None
    assert hold.reason == "Sensitive change: its settings or its diff cannot be read"
    assert hold.owner is True


async def test_a_config_that_cannot_be_read_holds_the_change(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, '[agents\nsensitive_paths = ["a"]\n')

    assert await stages.change_hold(branch.id, head(work)) == (
        "Sensitive change: its settings or its diff cannot be read"
    )


async def test_a_config_with_only_comments_holds_nothing(
    stages: StageService, branch: Ticket, work: Path
) -> None:
    configure(work, "# nothing set here\n\n")

    assert await stages.review_hold(branch.id, head(work), [], review_active=False) is None
    assert await stages.change_hold(branch.id, head(work)) is None
