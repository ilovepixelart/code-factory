"""The queue cards the board adapter reads: when a ticket is due a review run or a fix run.

Real tickets, stages and runs services on the test database; git facts and run ports are fakes.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app_lifespan import IDLE_MODULES
from code_factory.app import build_services
from code_factory.delivery.models import PullReading
from code_factory.delivery.service import DeliveryService
from code_factory.follower.models import Card
from code_factory.follower.service.neighbours import BoardAdapter, WorkAdapter
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine
from code_factory.platform.errors import ConflictError
from code_factory.platform.module import Resources
from code_factory.platform.services import Services
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.runs.adapters.processes import ProcessRegistry
from code_factory.runs.ports import TicketFacts
from code_factory.runs.repository import RunRepository
from code_factory.runs.service import RunService
from code_factory.runs.service.flow import FlowAdapter
from code_factory.settings.service import SettingsService
from code_factory.stages.service import Ports, StageService
from code_factory.talk.service import TalkService
from code_factory.tickets.models import (
    Finding,
    NewActivity,
    NewTicket,
    PullRequest,
    PullRequestState,
    Review,
    Ticket,
)
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)
from runs_fakes import Fakes
from runs_values import a_run
from stage_fakes import FakeFacts
from ticket_values import OWNER

CHANGES = Review(
    verdict="changes",
    summary="One gap.",
    findings=[Finding(severity="blocker", text="drops the lock", path="a.py", line=3)],
)


@pytest.fixture
async def checkout(tmp_path: Path, repositories: RepositoryService) -> Path:
    root = tmp_path / "sample"
    (root / ".code-factory").mkdir(parents=True)
    (root / ".code-factory" / "config.toml").write_text("[agents]\nreview = true\n")
    await repositories.track(root)
    return root


@pytest.fixture
def branch_facts() -> FakeFacts:
    return FakeFacts()


@pytest.fixture
def stages(  # noqa: PLR0913, PLR0917  # one fixture per service the module reads
    uow: UnitOfWork,
    tickets: TicketService,
    reviews: ReviewService,
    activity: ActivityService,
    documents: DocumentService,
    repositories: RepositoryService,
    branch_facts: FakeFacts,
) -> StageService:
    ports = Ports(
        tickets=tickets,
        reviews=reviews,
        activity=activity,
        documents=documents,
        releases=ReleaseService(uow, tickets),
        repositories=repositories,
        settings=SettingsService(uow),
        facts=branch_facts,
    )
    return StageService(uow, ports)


@pytest.fixture
def board(  # noqa: PLR0913, PLR0917  # every service the cards read
    uow: UnitOfWork,
    tickets: TicketService,
    stages: StageService,
    repositories: RepositoryService,
    checkout: Path,  # noqa: ARG001  # the repository must be tracked
    tmp_path: Path,
    documents: DocumentService,
) -> BoardAdapter:
    services = Services()
    services.add(TicketService, tickets)
    services.add(StageService, stages)
    services.add(RepositoryService, repositories)
    services.add(SettingsService, SettingsService(uow))
    services.add(TalkService, TalkService(uow))
    services.add(DocumentService, documents)
    runs = RunService(uow, Fakes(tmp_path).ports, ProcessRegistry(), state_dir=tmp_path / "state")
    services.add(RunService, runs)
    return BoardAdapter(services)


@pytest.fixture
async def in_review(tickets: TicketService) -> Ticket:
    made = await tickets.create(NewTicket(repository="sample", title="A ticket"), by=OWNER)
    await tickets.set_branch(made.id, "feat/one", by=OWNER)
    pull = PullRequest(number=4, state=PullRequestState.OPEN, url="https://github.com/o/r/pull/4")
    return await tickets.set_pull_request(made.id, pull, by=OWNER)


async def _ended(uow: UnitOfWork, ticket: Ticket, run_id: str, **fields: object) -> None:
    async with uow() as session:
        await RunRepository(session).insert(
            a_run(ticket.number, run_id, exit_code=0, ended_at=fields["started_at"], **fields)
        )


async def _card(board: BoardAdapter, ticket: Ticket) -> Card:
    return next(c for c in await board.cards() if c.id == ticket.id)


async def test_a_pr_merged_on_github_unblocks_a_ticket_even_after_archiving(
    board: BoardAdapter, tickets: TicketService, in_review: Ticket
) -> None:
    dependent = await tickets.create(
        NewTicket(repository="sample", title="Dependent", blocked_by=[in_review.id]), by=OWNER
    )
    assert (await _card(board, dependent)).open_blockers == (in_review.id,)
    assert in_review.pull_request is not None
    merged = in_review.pull_request.model_copy(update={"state": PullRequestState.MERGED})
    await tickets.set_pull_request(in_review.id, merged, by=OWNER)
    await tickets.archive(in_review.id, by=OWNER)

    assert not (await tickets.get(in_review.id)).merged
    assert (await _card(board, dependent)).open_blockers == ()


async def test_a_ticket_in_review_is_due_a_review_after_its_build_and_not_after_its_review(
    board: BoardAdapter, uow: UnitOfWork, in_review: Ticket
) -> None:
    start = datetime.now(UTC)
    await _ended(uow, in_review, "b00000000001", stage="build", started_at=start)

    built = await _card(board, in_review)
    await _ended(
        uow, in_review, "r00000000001", stage="review", started_at=start + timedelta(minutes=1)
    )
    reviewed = await _card(board, in_review)

    assert (built.stage, built.review_due) == ("review", True)
    assert reviewed.review_due is False


async def test_a_ticket_the_review_returned_is_due_a_fix_until_a_build_run_commits(
    board: BoardAdapter,
    uow: UnitOfWork,
    stages: StageService,
    reviews: ReviewService,
    in_review: Ticket,
) -> None:
    await reviews.submit_review(in_review.id, CHANGES, by="run:r00000000001")
    await stages.apply_review(in_review.id, "r00000000001", "h1")

    returned = await _card(board, in_review)
    later = datetime.now(UTC) + timedelta(hours=1)
    await _ended(uow, in_review, "b00000000002", stage="build", started_at=later, commits=["c1"])
    fixed = await _card(board, in_review)

    assert (returned.stage, returned.fix_due) == ("build", True)
    assert fixed.fix_due is False


@pytest.fixture
def repair_agents(tmp_path: Path) -> Fakes:
    return Fakes(tmp_path)


@pytest.fixture
def repair_board(
    settings: Settings, uow: UnitOfWork, stages: StageService, tmp_path: Path, repair_agents: Fakes
) -> Services:
    own = settings.model_copy(update={"state_dir": tmp_path / "repair-state"})
    services = build_services(
        Resources(own, create_engine(own), uow, BackgroundTasks()), IDLE_MODULES
    )
    services.add(StageService, stages)
    ports = replace(repair_agents.ports, flow=FlowAdapter(services))
    services.add(RunService, RunService(uow, ports, ProcessRegistry(), state_dir=own.state_dir))
    return services


async def test_the_board_selects_a_fast_failure_and_holds_the_next_conflict_at_the_cap(
    repair_board: Services,
    repair_agents: Fakes,
    in_review: Ticket,
    branch_facts: FakeFacts,
    checkout: Path,
) -> None:
    stages = repair_board.get(StageService)
    activity = repair_board.get(ActivityService)
    (checkout / ".code-factory" / "config.toml").write_text("[agents]\nfix_rounds = 1\n")
    board = BoardAdapter(repair_board)
    branch_facts.give(in_review.id, head="h1", local=True, pushed=True, has_commits=True)
    await stages.observe([in_review.id])
    await activity.append(
        in_review.id,
        NewActivity(kind="checks", data={"commit": "h1", "exit_code": 1, "scope": "fast"}),
        by="board",
    )

    failed = await _card(board, in_review)
    assert (failed.stage, failed.fix_due, failed.repair_hold) == ("build", True, "")
    assert failed.repair is not None
    assert (failed.repair.head, failed.repair.reason) == ("h1", "ci")
    assert await stages.checks_task(in_review.id, "h1") is not None
    repair_agents.tickets.facts_by_id[in_review.id] = TicketFacts(
        id=in_review.id,
        number=in_review.number,
        repository=in_review.repository,
        title=in_review.title,
        kind="feature",
        branch=in_review.branch,
    )
    repair_agents.trees.heads = ["h1"]
    work = WorkAdapter(repair_board)
    await work.start(in_review.id, "build", failed.repair)
    (round_,) = (await stages.ledger(in_review.id)).rounds
    await repair_board.get(RunService).stop(round_.run_id)
    assert repair_agents.agents.plans[0].nudge == await stages.checks_task(in_review.id, "h1")

    await activity.append(
        in_review.id,
        NewActivity(kind="checks", data={"commit": "h1", "exit_code": 0}),
        by="board",
    )
    with pytest.raises(ConflictError, match="repair evidence changed"):
        await work.start(in_review.id, "build", failed.repair)
    assert len((await stages.ledger(in_review.id)).rounds) == 1

    branch_facts.give(in_review.id, head="h2", local=True, pushed=True, has_commits=True)
    await stages.observe([in_review.id])
    assert in_review.pull_request is not None
    await repair_board.get(DeliveryService).record_reading(
        in_review.id,
        in_review.repository,
        in_review.pull_request.url,
        PullReading(state="open", head="h2", conflict=True),
    )

    conflict = await _card(board, in_review)
    assert conflict.repair is not None
    assert (conflict.repair.head, conflict.repair.reason) == ("h2", "conflict")
    assert conflict.repair_hold == "Fix rounds exhausted (1) on h2"
    assert len((await stages.ledger(in_review.id)).halts) == 1
