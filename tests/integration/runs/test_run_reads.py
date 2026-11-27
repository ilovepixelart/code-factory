"""What the service answers about recorded runs."""

from datetime import timedelta
from pathlib import Path

import pytest

from code_factory.platform.errors import NotFoundError
from code_factory.runs.models import BudgetScope
from code_factory.runs.ports import Given, Settings, TicketFacts
from code_factory.runs.repository import RunEnd, RunRepository
from code_factory.runs.service import RunService
from runs_fakes import Fakes
from runs_values import NOW, a_run, at


async def seeded(run_repo: RunRepository, number: int) -> None:
    await run_repo.insert(a_run(number, "aaaaaaaaaaaa", started_at=at(1), attempt=0))
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(5), cost=1.5, tokens=100))
    await run_repo.insert(a_run(number, "bbbbbbbbbbbb", started_at=at(10), attempt=1))
    await run_repo.end("bbbbbbbbbbbb", RunEnd(exit_code=2, ended_at=at(15)))
    await run_repo.insert(a_run(number, "cccccccccccc", started_at=at(20), attempt=2))


async def test_a_tickets_runs_are_views_newest_first_in_one_state_each(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository
) -> None:
    await seeded(run_repo, facts.number)
    views = await runs.list_for_ticket(facts.id)
    assert [(v.id, v.state) for v in views] == [
        ("cccccccccccc", "running"),
        ("bbbbbbbbbbbb", "failed"),
        ("aaaaaaaaaaaa", "finished"),
    ]
    assert views[2].cost == 1.5
    assert views[2].ticket_id == facts.id


async def test_a_ticket_s_runs_can_be_filtered_by_state_and_capped(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository
) -> None:
    await seeded(run_repo, facts.number)
    assert [v.id for v in await runs.list_for_ticket(facts.id, state="failed")] == ["bbbbbbbbbbbb"]
    assert [v.id for v in await runs.list_for_ticket(facts.id, limit=1)] == ["cccccccccccc"]


async def test_the_board_cards_get_their_runs_by_ticket_id(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository
) -> None:
    await seeded(run_repo, facts.number)
    cards = await runs.card_runs([facts.id, "CF-999999"])
    assert [v.id for v in cards[facts.id]] == ["cccccccccccc", "bbbbbbbbbbbb", "aaaaaaaaaaaa"]
    assert cards["CF-999999"] == []


async def test_the_runs_started_in_a_window_of_one_stage_are_listed_oldest_first(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository
) -> None:
    await seeded(run_repo, facts.number)
    await run_repo.insert(a_run(None, "dddddddddddd", stage="coordinate", started_at=at(12)))
    found = await runs.build_starts("sample", at(1), at(20))
    assert [r.id for r in found] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]


async def test_usage_rows_and_csv_come_from_the_recorded_runs(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository
) -> None:
    await run_repo.insert(
        a_run(facts.number, "aaaaaaaaaaaa", agent="writer", model="m", started_at=NOW)
    )
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(5), cost=1.256, tokens=150))
    (row,) = await runs.usage()
    assert (row.day, row.agent, row.model, row.runs, row.tokens) == (
        "2026-11-23",
        "writer",
        "m",
        1,
        150,
    )
    assert await runs.usage_csv() == (
        "day,agent,model,runs,tokens,cost\n2026-11-23,writer,m,1,150,1.26\n"
    )


async def test_the_months_budget_is_its_cap_and_what_the_repositorys_runs_spent(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.config.value = Settings(monthly_budget_usd=10.0)
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", started_at=NOW, attempt=0))
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(5), cost=4.0))
    await run_repo.insert(
        a_run(facts.number, "bbbbbbbbbbbb", started_at=NOW - timedelta(days=30), attempt=1, cost=9)
    )
    assert await runs.month_budget("sample", NOW) == BudgetScope(
        name="month", budget=10.0, spent=4.0, month="2026-11"
    )


async def test_no_monthly_budget_is_none(runs: RunService) -> None:
    assert await runs.month_budget("sample", NOW) is None


async def test_a_review_is_unpaid_when_the_ticket_s_budget_is_spent(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"budget": "4"})
    await seeded(run_repo, facts.number)
    await run_repo.end("cccccccccccc", RunEnd(exit_code=0, ended_at=at(25), cost=3.0))
    unpaid = await runs.review_unpaid(facts.id, NOW)
    assert unpaid is not None
    assert unpaid.note == "budget reached ($4.50 of $4.00)"


async def test_a_review_is_unpaid_when_a_priced_runs_cost_is_unknown(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"budget": "10"})
    fakes.agents.given_value = Given(
        agent="writer",
        runtime="claude",
        model="m",
        connection="c",
        fingerprint="f",
        input_price=3.0,
        output_price=15.0,
    )
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", agent="writer", started_at=at(1)))
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(5)))
    unpaid = await runs.review_unpaid(facts.id, NOW)
    assert unpaid is not None
    assert unpaid.note == (
        "the ticket's budget ($10.00) cannot be judged: run aaaaaaaaaaaa recorded no cost"
    )


async def test_a_free_agent_s_unknown_cost_does_not_stop_a_review(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"budget": "10"})
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", agent="writer", started_at=at(1)))
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(5)))
    assert await runs.review_unpaid(facts.id, NOW) is None


async def test_the_log_is_its_last_mebibyte_from_a_line_start(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository, tmp_path: Path
) -> None:
    log = tmp_path / "state" / "runs" / "aaaaaaaaaaaa.log"
    log.parent.mkdir(parents=True)
    line = "x" * 99 + "\n"
    log.write_text(line * 20_000)
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", log=str(log)))
    text = await runs.log("aaaaaaaaaaaa")
    assert len(text) <= 1024 * 1024
    assert text.startswith("x" * 99 + "\n")
    assert text.endswith("\n")


@pytest.mark.parametrize("bad", ["../etc/passwd", "a b", "", "a/b", "ab%20"])
async def test_a_run_id_that_is_not_letters_and_digits_names_no_run(
    runs: RunService, bad: str
) -> None:
    with pytest.raises(NotFoundError, match=f"no run {bad}"):
        await runs.log(bad)


async def test_a_log_not_written_yet_is_an_empty_text(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository, tmp_path: Path
) -> None:
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", log=str(tmp_path / "missing.log")))
    assert await runs.log("aaaaaaaaaaaa") == ""


async def test_an_unknown_run_has_no_log(runs: RunService) -> None:
    with pytest.raises(NotFoundError, match="no run 000000000000"):
        await runs.log("000000000000")


async def test_active_runs_say_whether_their_process_lives(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "sleep 30"
    (run,) = (await runs.start(facts.id)).runs
    (active,) = await runs.active_runs()
    assert (active.run.id, active.alive) == (run.id, True)


async def test_a_ticket_id_with_non_ascii_digits_names_no_ticket(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository
) -> None:
    await seeded(run_repo, facts.number)
    arabic = "CF-" + str(facts.number).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
    assert (await runs.card_runs([arabic]))[arabic] == []
    with pytest.raises(NotFoundError, match="no such ticket"):
        await runs.list_for_ticket(arabic)


async def test_an_agent_with_half_a_price_is_not_priced(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"budget": "10"})
    fakes.agents.given_value = Given(
        agent="writer",
        runtime="claude",
        model="m",
        connection="c",
        fingerprint="f",
        input_price=3.0,
    )
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", agent="writer", started_at=at(1)))
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(5)))
    assert await runs.review_unpaid(facts.id, NOW) is None
