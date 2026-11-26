"""The fix loop over the database: rounds decided under the ticket's lock, halts recorded once, the
head's checks read from the ledger, the task the agent is told. Sentences and caps are the previous
implementation's (`[agents] fix_rounds` default 3)."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.stages.models import PullView
from code_factory.stages.service import StageService
from code_factory.tickets.models import NewActivity, Ticket
from code_factory.tickets.service import ActivityService
from stage_fakes import FakeClock
from stage_values import NOW


async def record(
    activity: ActivityService,
    ticket: Ticket,
    kind: str,
    at: datetime | None = None,
    **data: object,
) -> None:
    await activity.append(ticket.id, NewActivity(kind=kind, data=dict(data), at=at), by="board")


def configure(checkout: Path, text: str) -> None:
    (checkout / ".code-factory").mkdir()
    (checkout / ".code-factory" / "config.toml").write_text(text)


async def test_a_round_is_started_one_below_the_cap_and_counted(
    stages: StageService, started: Ticket
) -> None:
    for head in ("h1", "h2"):
        assert (await stages.begin_fix_round(started.id, head, "ci")).outcome == "started"

    third = await stages.begin_fix_round(started.id, "h3", "ci")

    assert (third.outcome, third.rounds) == ("started", 3)


async def test_at_the_cap_the_rounds_are_halted_once_and_nothing_more_is_given(
    stages: StageService, started: Ticket
) -> None:
    for head in ("h1", "h2", "h3"):
        await stages.begin_fix_round(started.id, head, "ci")

    first = await stages.begin_fix_round(started.id, "h4", "ci")
    again = await stages.begin_fix_round(started.id, "h4", "ci")

    assert (first.outcome, first.rounds) == ("halted", 3)
    assert again.outcome == "halted"
    ledger = await stages.ledger(started.id)
    assert [(h.head, h.reason, h.rounds) for h in ledger.halts] == [("h4", "ci", 3)]
    assert len(ledger.rounds) == 3


async def test_the_cap_is_the_repositorys_fix_rounds_setting(
    stages: StageService, started: Ticket, checkout: Path
) -> None:
    configure(checkout, "[agents]\nfix_rounds = 1\n")

    assert (await stages.begin_fix_round(started.id, "h1", "ci")).outcome == "started"
    assert (await stages.begin_fix_round(started.id, "h2", "ci")).outcome == "halted"


async def test_a_round_that_cannot_start_waits_and_records_nothing(
    stages: StageService, started: Ticket
) -> None:
    decision = await stages.begin_fix_round(started.id, "h1", "ci", can_start=False)

    assert decision.outcome == "waiting"
    ledger = await stages.ledger(started.id)
    assert (ledger.rounds, ledger.halts) == ([], [])


async def test_a_head_has_one_round_per_reason_and_asking_again_is_given(
    stages: StageService, started: Ticket
) -> None:
    await stages.begin_fix_round(started.id, "h1", "ci", run_id="r1")

    again = await stages.begin_fix_round(started.id, "h1", "ci", run_id="r2")
    other = await stages.begin_fix_round(started.id, "h1", "conflict")

    assert (again.outcome, again.rounds) == ("given", 1)
    assert (other.outcome, other.rounds) == ("started", 2)
    assert [r.run_id for r in (await stages.ledger(started.id)).rounds] == ["r1", ""]


async def test_each_review_stamp_has_its_own_round_on_the_same_head(
    stages: StageService, started: Ticket
) -> None:
    first = await stages.begin_fix_round(started.id, "h1", "review", review="s1")
    second = await stages.begin_fix_round(started.id, "h1", "review", review="s2")
    again = await stages.begin_fix_round(started.id, "h1", "review", review="s1")

    assert [d.outcome for d in (first, second, again)] == ["started", "started", "given"]


async def test_a_review_stamp_already_given_a_round_on_another_head_is_given_not_started(
    stages: StageService, started: Ticket
) -> None:
    await stages.begin_fix_round(started.id, "h1", "review", review="s1")

    carried = await stages.begin_fix_round(started.id, "h2", "review", review="s1")

    assert (carried.outcome, carried.rounds) == ("given", 1)
    assert len((await stages.ledger(started.id)).rounds) == 1


async def test_a_round_needs_a_head_and_a_known_reason(
    stages: StageService, started: Ticket
) -> None:
    with pytest.raises(BadRequestError, match="needs a head and a reason of ci, review, conflict"):
        await stages.begin_fix_round(started.id, "h1", "tired")
    with pytest.raises(BadRequestError, match="needs a head"):
        await stages.begin_fix_round(started.id, "", "ci")


async def test_a_round_for_a_ticket_that_does_not_exist_is_not_found(stages: StageService) -> None:
    with pytest.raises(NotFoundError):
        await stages.begin_fix_round("CF-99999", "h1", "ci")


async def test_a_round_given_and_the_rounds_out_read_what_was_recorded(
    stages: StageService, started: Ticket
) -> None:
    for head in ("h1", "h2", "h3"):
        await stages.begin_fix_round(started.id, head, "review", review=f"s-{head}")
    await stages.begin_fix_round(started.id, "h4", "review", review="s-h4")
    pull = PullView(head="h4", review="changes_requested", reviewed="s-h4")

    assert await stages.round_given(started.id, PullView(head="h1", reviewed="s-h1"), "review")
    assert not await stages.round_given(started.id, pull, "review")
    assert await stages.rounds_out(started.id, pull) == (
        "Fixes stopped after 3 rounds: a review still requests changes"
    )
    assert await stages.rounds_out(started.id, PullView(head="h4")) is None
    assert await stages.halted_at(started.id, "h4") == NOW
    assert await stages.halted_at(started.id, "h1") is None


async def test_a_wait_on_main_is_kept_per_head_and_the_latest_write_wins(
    stages: StageService, started: Ticket, clock: FakeClock
) -> None:
    await stages.note_waits_on_main(started.id, "h1", "rust-fmt", "m1")
    clock.advance(5)
    await stages.note_waits_on_main(started.id, "h1", "rust-test", "m2")

    assert await stages.waits_on_main(started.id, "h1") == "Fails on main too at rust-test"
    assert await stages.waits_on_main(started.id, "h2") is None
    assert [(w.step, w.main_commit) for w in (await stages.ledger(started.id)).waits] == [
        ("rust-test", "m2")
    ]


async def test_the_checks_state_of_a_head_reads_the_ledger(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    await record(
        activity,
        started,
        "checks",
        commit="h1",
        tree_id="t1",
        exit_code=1,
        steps={"fmt": "passed", "web": "failed"},
    )

    state = await stages.checks_state(started.id, "h1", NOW)

    assert (state.exit_code, state.settled, state.rerun_pending) == (1, False, True)
    assert state.failed_steps == ["web"]
    other = await stages.checks_state(started.id, "h2", NOW)
    assert (other.exit_code, other.settled, other.rerun_pending) == (None, False, False)


async def test_a_container_that_was_unavailable_is_retried_a_minute_later(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    await record(
        activity,
        started,
        "checks",
        commit="h1",
        tree_id="t1",
        exit_code=-1,
        reason="checks container unavailable",
        at=NOW,
    )

    early = await stages.checks_state(started.id, "h1", NOW + timedelta(seconds=59))
    due = await stages.checks_state(started.id, "h1", NOW + timedelta(seconds=60))

    assert (early.container_retry_due, due.container_retry_due) == (False, True)


async def test_a_failure_before_a_pass_on_a_tree_is_the_flaky_reading(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    await record(activity, started, "checks", commit="h1", exit_code=1, tree="t1", log="log-a")
    await record(activity, started, "checks", commit="h1", exit_code=0, tree="t1", log="log-p")

    found = await stages.flaky(started.id, "t1")

    assert found is not None
    assert found.log == "log-a"
    assert found.reason == (
        f"Filed by the board when the checks of {started.id} passed on tree t1 after failing "
        "there. The failed run is logged at log-a."
    )
    assert await stages.flaky(started.id, "t2") is None


class Logs:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.asked: list[str] = []

    async def read(self, log: str) -> str | None:
        self.asked.append(log)
        return self.text


async def test_the_checks_task_quotes_the_failed_steps_and_the_masked_failing_lines(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    logs = Logs(
        'gate: rust-test starts\nerror: {"token": "abc123"}\ngate: rust-test failed (exit 101)\n'
    )
    stages.bind_log_reader(logs)
    await record(
        activity,
        started,
        "checks",
        commit="0123456789abcdef",
        exit_code=101,
        log="checks/sample-CF-1-1.log",
        steps={"rust-test": "failed"},
    )

    task = await stages.checks_task(started.id, "0123456789abcdef")

    assert logs.asked == ["checks/sample-CF-1-1.log"]
    assert task == (
        "The board's checks failed on 0123456789ab at rust-test (exit 101). Their log says:\n"
        'error: {"token": "[redacted]"}\n'
        "gate: rust-test failed (exit 101)\n"
        "Fix the cause on this branch, and keep every test green."
    )


async def test_the_checks_task_without_a_log_reader_or_a_readable_log_quotes_none(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    await record(
        activity, started, "checks", commit="h1", exit_code=1, log="x.log", steps={"web": "failed"}
    )
    expected = (
        "The board's checks failed on h1 at web (exit 1). "
        "Fix the cause on this branch, and keep every test green."
    )

    assert await stages.checks_task(started.id, "h1") == expected
    stages.bind_log_reader(Logs(None))
    assert await stages.checks_task(started.id, "h1") == expected


async def test_there_is_no_task_for_a_head_whose_checks_passed_or_never_ran(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    await record(activity, started, "checks", commit="h1", exit_code=0)

    assert await stages.checks_task(started.id, "h1") is None
    assert await stages.checks_task(started.id, "h2") is None
