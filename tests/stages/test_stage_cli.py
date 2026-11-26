"""`code-factory stage show|observe|rounds`: the lines a person reads."""

import argparse

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.services import Services
from code_factory.stages.cli import stage_command
from code_factory.stages.service import StageService
from code_factory.tickets.models import Ticket
from stage_fakes import FakeFacts


def parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="stage")
    stage_command.configure(parser)
    return parser.parse_args(argv)


@pytest.fixture
def services(stages: StageService) -> Services:
    registry = Services()
    registry.add(StageService, stages)
    return registry


async def run(services: Services, *argv: str) -> int:
    run_async = stage_command.run_async
    assert run_async is not None
    return await run_async(parse(*argv), services)


async def test_show_prints_the_stage_checklist_refusals_and_hold(
    services: Services, started: Ticket, facts: FakeFacts, capsys: pytest.CaptureFixture[str]
) -> None:
    facts.give(started.id, local=True)
    await services.get(StageService).observe()

    assert await run(services, "show", started.id) == 0

    assert capsys.readouterr().out == (
        f"{started.id} stage build (derived build, declared none)\n"
        "facts known, observed 2026-11-23 09:30:00+00:00\n"
        "work done: no\n"
        "checklist:\n"
        "  spec: present: a branch\n"
        f"  build: absent: a commit on {started.branch}\n"
        f"  review: absent: a push of {started.branch} and a pull request\n"
        "  merged: absent: a merge into main\n"
        "  released: absent (optional): a release note naming it\n"
        "refusals:\n"
        "  spec: none\n"
        "  build: none\n"
        f"  review: {started.id} needs a commit on {started.branch} before Review\n"
        f"  merged: {started.id} moves one column at a time: Review is next\n"
        f"hold: needs build: a commit on {started.branch}\n"
    )


async def test_observe_prints_the_count_and_each_presence_change(
    services: Services, started: Ticket, facts: FakeFacts, capsys: pytest.CaptureFixture[str]
) -> None:
    facts.give(started.id, local=True, has_commits=True)

    assert await run(services, "observe", started.id) == 0
    assert capsys.readouterr().out == (
        f"observed 1 tickets, 0 unreadable\n{started.id} spec present\n{started.id} build present\n"
    )
    assert await run(services, "observe") == 0
    assert capsys.readouterr().out == "observed 1 tickets, 0 unreadable\n"


async def test_rounds_prints_the_fix_rounds_halts_waits_and_verdicts(
    services: Services, started: Ticket, capsys: pytest.CaptureFixture[str]
) -> None:
    stages = services.get(StageService)
    await stages.begin_fix_round(started.id, "0123456789", "ci")
    await stages.note_waits_on_main(started.id, "0123456789", "rust-test", "m1")
    await stages.record_review_skipped(started.id, "abcdefghij", "budget", "budget spent")

    assert await run(services, "rounds", started.id) == 0

    assert capsys.readouterr().out == (
        "fix rounds:\n  ci on 0123456\nhalts:\nwaits on main:\n  0123456 at rust-test\n"
        "review verdicts:\n  skipped abcdefg budget spent\n"
    )


@pytest.mark.parametrize("action", ["show", "rounds"])
async def test_an_unknown_ticket_is_one_sentence_the_command_line_prints(
    services: Services, action: str
) -> None:
    with pytest.raises(NotFoundError, match="CF-99999 does not exist"):
        await run(services, action, "CF-99999")


async def test_a_name_that_is_no_ticket_id_is_refused(services: Services) -> None:
    with pytest.raises(BadRequestError, match="is not a ticket id"):
        await run(services, "show", "nonsense")
