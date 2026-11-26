"""`code-factory memory review`: the review queue, the pairs and the consolidation proposals."""

import argparse
import json

import pytest

from code_factory.memory_extras.cli import memory_command
from code_factory.memory_extras.models import TicketContext
from code_factory.memory_extras.service import MemoryExtrasService
from code_factory.platform.errors import NotFoundError
from code_factory.platform.services import Services
from memory_extras_bench import Bench
from memory_extras_values import NOW

SQUASH = "Squash ticket branches before landing them through the merge queue"
QUEUE = "Never let the merge queue take ticket branches unsquashed"


async def review(bench: Bench, *argv: str) -> int:
    services = Services()
    services.add(MemoryExtrasService, bench.service)
    parser = argparse.ArgumentParser(prog="memory")
    memory_command.configure(parser)
    run_async = memory_command.run_async
    assert run_async is not None
    return await run_async(parser.parse_args(["review", *argv]), services)


async def fixture(bench: Bench) -> None:
    await bench.seed("2026-08-11-old-rule", "Old rule", reviewed="2026-08-11")
    await bench.seed("2026-10-01-squash", SQUASH, reviewed="2026-11-09")
    await bench.seed("2026-10-05-queue", QUEUE, reviewed="2026-11-09")
    await bench.seed(
        "2026-09-01-gate",
        "Run the gate before every push of a ticket branch",
        reviewed="2026-11-09",
    )
    await bench.seed(
        "2026-09-05-gate-each",
        "Run the gate before each push of the ticket branch",
        reviewed="2026-11-09",
    )
    await bench.seed("2026-09-02-other", "Other", reviewed="2026-11-09", repository="second")
    await bench.service.deliver("run-1", "CF-1", "sample", TicketContext(), now=NOW)


async def test_the_review_lists_the_queue_then_the_pairs_then_the_proposals_and_exits_zero(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    await fixture(bench)
    assert await review(bench, "--repository", "sample") == 0
    assert capsys.readouterr().out == (
        "review queue:\n"
        "sample 2026-08-11-old-rule due 2026-11-09: overdue\n"
        "pairs:\n"
        "sample may contradict: 2026-10-01-squash and 2026-10-05-queue "
        "(branches, merge, queue, ticket)\n"
        "proposals:\n"
        "sample merge 2026-09-05-gate-each into 2026-09-01-gate\n"
    )


async def test_a_pair_that_does_not_contradict_is_printed_as_on_one_subject(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    await bench.seed("2026-10-01-squash", SQUASH, reviewed="2026-11-09")
    await bench.seed(
        "2026-10-05-queue",
        "The merge queue takes ticket branches as they are",
        reviewed="2026-11-09",
    )
    assert await review(bench, "--repository", "sample") == 0
    assert capsys.readouterr().out == (
        "review queue:\n"
        "sample 2026-10-01-squash due 2027-02-07: unused\n"
        "sample 2026-10-05-queue due 2027-02-07: unused\n"
        "pairs:\n"
        "sample on one subject: 2026-10-01-squash and 2026-10-05-queue "
        "(branches, merge, queue, ticket)\n"
    )


async def test_the_review_names_unused_and_stale_cites_as_reasons(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    await bench.seed("2026-01-01-idle", "Idle", reviewed="2026-11-09")
    await bench.seed(
        "2026-11-01-cites", "Cites", reviewed="2026-11-09", cites=["gone.py", "also_gone"]
    )
    assert await review(bench, "--repository", "sample") == 0
    assert capsys.readouterr().out == (
        "review queue:\n"
        "sample 2026-01-01-idle due 2027-02-07: unused\n"
        "sample 2026-11-01-cites due 2027-02-07: cites gone: gone.py, also_gone\n"
    )


async def test_without_a_repository_every_tracked_one_is_reviewed(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    await fixture(bench)
    assert await review(bench) == 0
    out = capsys.readouterr().out
    assert "second 2026-09-02-other" in out
    assert "sample 2026-08-11-old-rule" in out


async def test_nothing_to_review_says_so(bench: Bench, capsys: pytest.CaptureFixture[str]) -> None:
    assert await review(bench) == 0
    assert capsys.readouterr().out == "nothing to review\n"


async def test_json_prints_the_three_lists(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    await fixture(bench)
    assert await review(bench, "--repository", "sample", "--json") == 0
    answer = json.loads(capsys.readouterr().out)
    assert list(answer) == ["review_queue", "pairs", "proposals"]
    assert [r["id"] for r in answer["review_queue"]] == ["2026-08-11-old-rule"]
    assert answer["pairs"][0]["contradicts"] is True
    assert answer["proposals"][0]["action"] == "merge"


async def test_an_unknown_repository_is_refused_with_a_sentence(bench: Bench) -> None:
    with pytest.raises(NotFoundError, match=r"^nowhere is not a tracked repository$"):
        await review(bench, "--repository", "nowhere")
