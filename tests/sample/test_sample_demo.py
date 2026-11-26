"""The `demo` sample: a board in use, so every page of the web app has something to show.

Expected values come from what the sample files (its titles, questions, sessions) and from the
domain's own rules (a pass review moves nothing, a changes review sends the ticket to Build).
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app_lifespan import IDLE_MODULES
from code_factory.agents.service import AgentService
from code_factory.app import build_services
from code_factory.board.service import BoardService
from code_factory.factory.service import FactoryService
from code_factory.inbox.service import InboxService
from code_factory.memory.models import MemoryFilter
from code_factory.memory.service import MemoryService
from code_factory.metrics.service import MetricsService
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.config import Settings
from code_factory.platform.db import Base, UnitOfWork, create_engine
from code_factory.platform.module import Resources
from code_factory.platform.services import Services
from code_factory.releases.service import ReleaseService
from code_factory.sample.service import SampleService
from code_factory.sessions.service import SessionService
from code_factory.stages.service import StageService
from code_factory.talk.service import TalkService
from code_factory.team.service import TeamService
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import Column, TicketFilter
from code_factory.tickets.service import TicketService

# The tables the demo leaves empty, each with the reason. A table missing from here that is empty
# after the load fails the test, so a page whose source the demo stops filling is noticed.
LEFT_EMPTY = {
    "run_previews": "a preview belongs to a run",
    "permission_requests": "a permission request belongs to a run",
    "permission_reviews": "a permission review belongs to a run",
    "permission_decisions": "a permission decision belongs to a run",
    "permission_rules": "a standing rule is adopted from answered permission requests",
    "agent_context_versions": "written when an agent's context is replaced",
    "agent_model_checks": "written when a connection is probed over the network",
    "board_settings": "the board's own settings; defaults hold",
    "intake_key_grants": "intake keys reach outside services",
    "broker_tokens": "issued to a running agent",
    "check_claims": "remote check runners",
    "check_declines": "remote check runners",
    "check_offers": "remote check runners",
    "check_verify_runs": "verification runs follow a fix round",
    "check_main_records": "main checks run on the default branch by the follower",
    "delivery_events": "delivery reads GitHub, which the demo repositories are not on",
    "delivery_intake": "delivery reads GitHub, which the demo repositories are not on",
    "delivery_issue_status": "delivery reads GitHub, which the demo repositories are not on",
    "delivery_polls": "delivery reads GitHub, which the demo repositories are not on",
    "eval_judge_days": "the scheduled judge claims a day when it runs",
    "eval_records": "benchmark records come from eval suites, not built yet",
    "eval_task_runs": "benchmark task runs come from eval suites, not built yet",
    "fix_halts": "fix rounds follow failing checks on a run's head",
    "fix_rounds": "fix rounds follow failing checks on a run's head",
    "fix_waits": "fix rounds follow failing checks on a run's head",
    "follower_queue_plan": "written by the follower's pass while agents run",
    "git_merge_checks": "written when the board lands a branch",
    "git_trees": "written when the board makes a run's worktree",
    "memory_deliveries": "written when a run's session loads memory",
    "push_failures": "push sends to ntfy or a webhook outside this machine",
    "push_sent": "push sends to ntfy or a webhook outside this machine",
    "push_targets": "push sends to ntfy or a webhook outside this machine",
    "reply_tokens": "reply links are minted for push messages",
    "session_rejects": "a reject is a malformed hook payload",
    "session_run_requests": "a run's telemetry export",
    "talk_news_marks": "news is read by a running agent",
    "team_lease_runs": "a lease run belongs to a run",
    "undo_entries": "written by the owner's edits in the web app",
    "ticket_mock_files": "mock files are uploaded by an agent's spec run",
}


@pytest.fixture
async def demo(
    settings: Settings, uow: UnitOfWork, tmp_path: Path
) -> tuple[Services, dict[str, str]]:
    """The services as `app.py` wires them, the demo loaded, its git under the test's folder."""
    own = settings.model_copy(update={"state_dir": tmp_path / "state"})
    resources = Resources(own, create_engine(own), uow, BackgroundTasks())
    services = build_services(resources, IDLE_MODULES)
    return services, await services.get(SampleService).load("demo")


@pytest.mark.usefixtures("demo")
async def test_every_table_a_page_reads_holds_rows_and_the_rest_say_why_not(
    connection: AsyncConnection,
) -> None:
    empty = set()
    for table in Base.metadata.sorted_tables:
        if await connection.scalar(select(func.count()).select_from(table)) == 0:
            empty.add(table.name)
    assert empty - set(LEFT_EMPTY) == set(), "filled by no page's source"
    assert set(LEFT_EMPTY) - empty == set(), "listed as empty but filled"


async def test_the_board_holds_tickets_in_every_column_across_three_repositories(
    demo: tuple[Services, dict[str, str]],
) -> None:
    services, ids = demo
    tickets = await services.get(TicketService).list(TicketFilter(archived=None))
    by_title = {t.title: t for t in tickets}

    assert {t.repository for t in tickets} == {"shop-api", "web", "infra"}
    assert len(tickets) == len(ids) == 25
    assert by_title["Gift cards"].column is Column.SPEC
    assert by_title["Pay part of an order with a gift card"].column is Column.BUILD
    assert by_title["Issue a gift card code on purchase"].column is Column.REVIEW
    assert by_title["Export orders as CSV"].column is Column.MERGED
    assert by_title["Pay part of an order with a gift card"].blocked_by == [
        ids["Issue a gift card code on purchase"]
    ]
    assert await services.get(BoardService).list_views() == [
        {"name": "High priority", "query": "priority=high"},
        {"name": "Storefront", "query": "repository=web"},
    ]
    assert await services.get(TicketWriteService).column_limits() == {"build": 4}


async def test_a_pass_review_is_passed_and_a_changes_review_is_returned_on_the_reviewed_head(
    demo: tuple[Services, dict[str, str]],
) -> None:
    services, ids = demo
    stages = services.get(StageService)
    passed = await stages.review_verdicts(ids["Issue a gift card code on purchase"])
    returned = await stages.review_verdicts(
        ids["Checkout keeps the address after a failed payment"]
    )

    assert [v.outcome for v in passed] == ["passed"]
    assert [v.outcome for v in returned] == ["returned"]
    assert len(passed[0].head) == len(returned[0].head) == 40  # a git commit id


async def test_the_inbox_holds_the_open_questions_the_proposal_and_the_capture(
    demo: tuple[Services, dict[str, str]],
) -> None:
    services, _ = demo
    sections = await services.get(InboxService).page()
    questions = [item["question"]["text"] for item in sections["questions"]]

    assert sorted(questions) == [
        "Do gift cards expire?",
        "Keep the old staging running until the move is checked?",
        "What may someone with the link do to the wishlist?",
        "Which is spent first when an order has a gift card and a coupon?",
        "Which layout should the export use?",
    ]
    assert [item["memory"]["statement"] for item in sections["memory"]] == [
        "Read the shop's timezone from settings, never from the server"
    ]
    assert [item["images"] for item in sections["screens"]] == [["home.png", "product.png"]]
    assert [item["ticket"]["title"] for item in sections["mergeable"]] == [
        "Issue a gift card code on purchase"
    ]
    assert [item["ticket"]["title"] for item in sections["failing"]] == [
        "Rotate the payment provider keys every 90 days"
    ]
    assert [item["ticket"]["title"] for item in sections["idle"]] == [
        "Search ranks in-stock products first"
    ]
    assert sections["diagnoses"]


async def test_sessions_carry_the_transcripts_tokens_and_the_reported_cost(
    demo: tuple[Services, dict[str, str]],
) -> None:
    services, _ = demo
    sessions = services.get(SessionService)
    usage = await sessions.usage(("demo-checkout-address",))

    # Three messages of (input, output, cache read, cache write) at the sonnet prices per million.
    assert usage["demo-checkout-address"]["output"] == 900 + 1400 + 600
    tokens = ((5200, 900, 42000, 3100), (2100, 1400, 51000, 900), (1800, 600, 53000, 0))
    prices = (3.0, 15.0, 0.3, 3.75)
    cost = sum(n * p for message in tokens for n, p in zip(message, prices, strict=True)) / 1e6
    assert usage["demo-checkout-address"]["cost"] == pytest.approx(cost)


async def test_the_flow_counts_the_merges_of_the_last_week(
    demo: tuple[Services, dict[str, str]],
) -> None:
    services, _ = demo
    flow = await services.get(MetricsService).flow("7d")

    # Merged 2 and 5 days before the load: the coupon fix and the lazy images.
    assert sorted(row.title for row in flow.merged) == [
        "Coupons expire at the end of their day in the shop's timezone",
        "Product images load lazily below the fold",
    ]
    assert all(row.from_ == "filed" for row in flow.merged)
    assert all(row.autonomy != "unknown" for row in flow.merged)
    assert flow.columns.review is not None


async def test_demo_analytics_has_populated_run_cost_review_and_response_sections(
    demo: tuple[Services, dict[str, str]],
) -> None:
    services, _ = demo
    factory = await services.get(FactoryService).dashboard(None, None)
    response_times = await services.get(TalkService).question_wait(
        datetime.now(UTC) - timedelta(days=7), datetime.now(UTC)
    )

    assert factory.runs.total > 0
    assert {row.key for row in factory.runs.by_state} == {"finished", "failed"}
    assert factory.prs.merged > 0
    assert factory.prs.closed == 1
    assert factory.cost.priced > 0
    assert factory.expensive
    assert {row.role for row in factory.role_notes} == {"qa", "security", "tests"}
    assert sum(row.fixed for row in factory.role_notes) == 1
    assert response_times.answered == 3
    assert response_times.median_seconds == 42 * 60
    assert {step.step for step in await services.get(MetricsService).step_times(25)} == {
        "prepare",
        "static",
        "pytest",
        "web",
    }


async def test_memory_agents_team_and_releases_hold_what_the_demo_filed(
    demo: tuple[Services, dict[str, str]],
) -> None:
    services, ids = demo
    entries = await services.get(MemoryService).list(MemoryFilter())
    agents = await services.get(AgentService).list_definitions()
    claims = await services.get(TeamService).list_claims()
    releases = await services.get(ReleaseService).list("shop-api")

    assert sorted(e.statement for e in entries) == [
        "Migrations that add a column with a default run in two steps",
        "Money is stored in integer cents, never floats",
        "Payments go through the provider's hosted fields only",
    ]
    assert [a.name for a in agents.agents] == ["builder", "reviewer"]
    assert {c.ticket_id for c in claims} == {
        ids["Pay part of an order with a gift card"],
        ids["Search ranks in-stock products first"],
    }
    published = next(r for r in releases if r.version == "1.3.0")
    draft = next(r for r in releases if r.version == "1.4.0")
    assert published.published_at is not None
    assert draft.published_at is None
    # The published release of shop-api names its two released tickets, which leave the board.
    assert sorted(published.tickets) == sorted(
        [ids["Checkout refunds partial orders"], ids["Rate limit the public search endpoint"]]
    )
