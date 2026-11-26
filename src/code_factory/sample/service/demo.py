"""The demo board, seeded through real git repositories, capture hooks and module services."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from code_factory.agents.models import AgentChange, ConnectionChange
from code_factory.agents.service import AgentService
from code_factory.board.service import BoardService
from code_factory.checks.service import CheckService
from code_factory.delivery.service import DeliveryService
from code_factory.evals.models import AnswerRow
from code_factory.evals.service import JudgeService
from code_factory.memory.models import NewMemory
from code_factory.memory.service import MemoryService
from code_factory.metrics.service import MetricsService
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.runs.service import RunService
from code_factory.sample.adapters import DemoGit, run_hook, write_png, write_transcript
from code_factory.sample.models.demo import (
    DEMO_AGENTS,
    DEMO_ANSWERS,
    DEMO_CHECKS,
    DEMO_COMMENTS,
    DEMO_CONNECTIONS,
    DEMO_DOCUMENTS,
    DEMO_MEMORY,
    DEMO_PROPOSALS,
    DEMO_QUESTIONS,
    DEMO_RELEASES,
    DEMO_REPOSITORIES,
    DEMO_REVIEWS,
    DEMO_SCORER,
    DEMO_SESSIONS,
    DEMO_TICKETS,
    DemoSession,
    DemoTicket,
    Stage,
)
from code_factory.sample.rules import pull_url, session_transcript, tool_input
from code_factory.sample.service.analytics import (
    IDLE_PULL,
    file_tickets,
    record_open_pull,
    record_pull_history,
    record_response_history,
    record_review_notes,
)
from code_factory.screens.service import ScreensService
from code_factory.sessions.service import SessionService
from code_factory.stages.service import StageService
from code_factory.talk.models import Choice
from code_factory.talk.service import TalkService
from code_factory.team.service import TeamService
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import (
    DocumentName,
    DocumentWrite,
    PullRequest,
    Review,
)
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)

_BUILDER = "run:builder"

AUTHOR = "demo"
HISTORY_DAYS = 60
BRANCHED_BEFORE_MERGE_DAYS = 1
CAPTURED = ("Dark theme for the storefront", ("home.png", "product.png"))
_LIVE = (Stage.BUILD, Stage.REVIEW)
# PostgreSQL's generic plan after five runs cannot match the partial queue index.
MOST_CHECK_RUNS = 5


@dataclass(frozen=True)
class DemoDeps:
    """The services the demo writes through."""

    tickets: TicketService
    tickets_at: Callable[[datetime], TicketService]
    board: BoardService
    writes: TicketWriteService
    documents: DocumentService
    activities: ActivityService
    reviews: ReviewService
    memory: MemoryService
    talk: TalkService
    talk_at: Callable[[datetime], TalkService]
    agents: AgentService
    team: TeamService
    repositories: RepositoryService
    releases: ReleaseService
    stages: StageService
    checks: CheckService
    metrics: MetricsService
    sessions: SessionService
    screens: ScreensService
    runs: RunService
    judge: JudgeService
    delivery: DeliveryService


def _config(name: str) -> str:
    scorer, question, stage = DEMO_SCORER
    return (
        f'[checks]\ncommand = "{DEMO_CHECKS[name]}"\ntimeout = 60\n\n'
        "[agents]\nsandbox = false\n\n"
        f'[[scorers]]\nname = "{scorer}"\nquestion = "{question}"\nstage = "{stage}"\n'
    )


def _branch(ticket_id: str) -> str:
    return f"ticket/{ticket_id.lower()}"


class DemoLoader:
    """Loads the demo into an empty prepared schema, its git and transcripts under `root`."""

    def __init__(self, deps: DemoDeps, root: Path, now: float) -> None:
        self._d = deps
        self._root = root
        self._now = now
        self._ids: dict[str, str] = {}
        self._git = {name: DemoGit(root / "repositories", name, now) for name in DEMO_REPOSITORIES}
        self._heads: dict[str, str] = {}

    async def load(self) -> dict[str, str]:
        """File everything; the id of each ticket by title."""
        at = datetime.fromtimestamp(self._now, UTC)
        self._ids = await file_tickets(self._d.tickets_at, at)
        await self._build_repositories()
        await self._settle(Stage.RELEASED)
        await self._release(published=True)
        await self._settle(Stage.MERGED)
        await self._release(published=False)
        await self._open_work()
        await self._write_documents()
        await self._ask_questions()
        await self._comment()
        await self._remember()
        await self._connect_agents()
        await self._review()
        await self._run_checks()
        await self._record_sessions()
        await self._capture_screens()
        await record_pull_history(self._d.delivery, self._d.runs, self._ids, self._heads, at)
        await record_response_history(self._d.talk_at, self._ids, at)
        reviewed = self._ticket("Product images load lazily below the fold")
        await record_review_notes(self._d.activities, self._d.reviews, reviewed)
        archived = self._ticket("Product page shows delivery estimate")
        await self._d.tickets.archive(archived, by=AUTHOR)
        await self._d.board.save_view("High priority", "priority=high")
        await self._d.board.save_view("Storefront", "repository=web")
        await self._d.writes.set_column_limit("build", 4, AUTHOR)
        await self._d.stages.observe()
        await self._d.metrics.refresh()
        # Keep the served demo from launching agents.
        await self._d.runs.stop_all(by=AUTHOR)
        return self._ids

    def _ticket(self, title: str) -> str:
        return self._ids[title]

    async def _build_repositories(self) -> None:
        for name, git in self._git.items():
            files = {
                "README.md": f"# {name}\n",
                ".gitignore": ".code-factory/worktrees/\n",
                ".code-factory/config.toml": _config(name),
            }
            await git.create(files, HISTORY_DAYS)
            await self._d.repositories.track(git.path)
        merged = [t for t in DEMO_TICKETS if t.stage in (Stage.MERGED, Stage.RELEASED)]
        for spec in sorted(merged, key=lambda t: -t.merged_days_ago):
            git, ticket = self._git[spec.repository], self._ticket(spec.title)
            branch = _branch(ticket)
            started = spec.merged_days_ago + BRANCHED_BEFORE_MERGE_DAYS
            self._heads[spec.title] = await git.branch(branch, spec.change, spec.title, started)
            await git.merge(branch, _number(ticket), spec.merged_days_ago)
        for spec in DEMO_TICKETS:
            if spec.stage in _LIVE:
                git, branch = self._git[spec.repository], _branch(self._ticket(spec.title))
                self._heads[spec.title] = await git.branch(branch, spec.change, spec.title, 1)
                if spec.stage is Stage.REVIEW:
                    await git.push(branch)

    def _pull(self, spec: DemoTicket, state: str) -> PullRequest:
        ticket = self._ticket(spec.title)
        return PullRequest.model_validate(
            {"number": _number(ticket), "state": state, "url": pull_url(spec.repository, ticket)}
        )

    async def _settle(self, stage: Stage) -> None:
        """Give each ticket of `stage` its branch, its merged pull request and the merge."""
        for spec in DEMO_TICKETS:
            if spec.stage is not stage:
                continue
            ticket = self._ticket(spec.title)
            await self._d.tickets.set_branch(ticket, _branch(ticket), by=AUTHOR)
            await self._d.tickets.set_pull_request(ticket, self._pull(spec, "merged"), by=AUTHOR)
            await self._d.tickets.set_merged(ticket, True, by=AUTHOR)

    async def _release(self, *, published: bool) -> None:
        """Draft a release of every repository with merged work no release names; publish it."""
        version = next(v for v, final in DEMO_RELEASES if final is published)
        stage = Stage.RELEASED if published else Stage.MERGED
        for name in sorted({t.repository for t in DEMO_TICKETS if t.stage is stage}):
            await self._d.releases.draft(name, version, by=AUTHOR)
            if published:
                await self._d.releases.publish(name, version, by=AUTHOR)

    async def _open_work(self) -> None:
        for spec in DEMO_TICKETS:
            if spec.stage not in _LIVE:
                continue
            ticket = self._ticket(spec.title)
            await self._d.tickets.set_branch(ticket, _branch(ticket), by=AUTHOR)
            if spec.stage is Stage.REVIEW or spec.title == IDLE_PULL:
                pull = self._pull(spec, "open")
                await self._d.tickets.set_pull_request(ticket, pull, by=AUTHOR)
                await record_open_pull(
                    self._d.delivery,
                    spec,
                    ticket,
                    self._heads[spec.title],
                    datetime.fromtimestamp(self._now, UTC),
                )

    async def _write_documents(self) -> None:
        for title, documents in DEMO_DOCUMENTS.items():
            for name, text in documents.items():
                write = DocumentWrite.model_validate({"content": text})
                await self._d.documents.write_document(
                    self._ticket(title), DocumentName(name), write, by=AUTHOR
                )

    async def _ask_questions(self) -> None:
        for asked in DEMO_QUESTIONS:
            offered = [
                Choice(text=c, recommended=best, description=why, preview=shown)
                for c, best, why, shown in asked["choices"]  # ty: ignore[not-iterable]
            ]
            await self._d.talk.ask(
                self._ticket(str(asked["title"])),
                str(asked["text"]),
                offered,
                document=str(asked.get("document") or "") or None,
                several=bool(asked.get("several")),
                topic=str(asked["topic"]),
                by=_BUILDER,
            )

    async def _comment(self) -> None:
        for title, text, path, line in DEMO_COMMENTS:
            ticket = self._ticket(title)
            if path:
                await self._d.talk.add_comment(ticket, text, "owner", path=path, line=line)
            else:
                await self._d.talk.add_comment(ticket, text, "owner")
        await self._d.activities.record_note(
            self._ticket("Move staging to the new cluster"),
            "Waiting for staging credentials from the provider.",
            "diagnosis",
            by=AUTHOR,
        )

    async def _remember(self) -> None:
        for entry in DEMO_MEMORY:
            new = NewMemory.model_validate({**entry, "repository": "shop-api"})
            await self._d.memory.add(new, by=AUTHOR)
        for entry in DEMO_PROPOSALS:
            new = NewMemory.model_validate({**entry, "repository": "shop-api"})
            await self._d.memory.propose(new, by=_BUILDER)

    async def _connect_agents(self) -> None:
        for connection in DEMO_CONNECTIONS:
            await self._d.agents.add_connection(ConnectionChange.model_validate(connection))
        for agent in DEMO_AGENTS:
            await self._d.agents.add_agent(AgentChange.model_validate(agent))
        for session in DEMO_SESSIONS:
            if not session.ended:
                await self._d.team.claim(self._ticket(session.ticket), "builder")

    async def _review(self) -> None:
        for at, (title, verdict, summary, findings) in enumerate(DEMO_REVIEWS, start=1):
            ticket, run = self._ticket(title), f"demo-review-{at}"
            review = Review.model_validate(
                {
                    "verdict": verdict,
                    "summary": summary,
                    "findings": [
                        {"severity": s, "text": text, "path": path, "line": line}
                        for s, text, path, line in findings
                    ],
                }
            )
            await self._d.reviews.submit_review(ticket, review, by=f"run:{run}")
            await self._d.stages.apply_review(ticket, run, self._heads[title])

    async def _run_checks(self) -> None:
        live = [spec for spec in DEMO_TICKETS if spec.stage in _LIVE]
        for spec in live[:MOST_CHECK_RUNS]:
            check = await self._d.checks.start(self._ticket(spec.title), by=AUTHOR)
            await self._d.checks.run_now(check)

    async def _record_sessions(self) -> None:
        hook = self._d.sessions.capture_hook().command
        for session in DEMO_SESSIONS:
            await self._record_session(hook, session)
        await self._d.sessions.ingest_once(wait=True)
        at = datetime.fromtimestamp(self._now, UTC)
        for session_id, answer, evidence in DEMO_ANSWERS:
            session = next(s for s in DEMO_SESSIONS if s.session_id == session_id)
            spec = next(t for t in DEMO_TICKETS if t.title == session.ticket)
            row = AnswerRow.model_validate(
                {
                    "session_id": session_id,
                    "scorer": DEMO_SCORER[0],
                    "answer": answer,
                    "evidence": evidence,
                    "at": at,
                }
            )
            await self._d.judge.record_answer(spec.repository, row)

    async def _record_session(self, hook: str, session: DemoSession) -> None:
        spec = next(t for t in DEMO_TICKETS if t.title == session.ticket)
        ticket = self._ticket(session.ticket)
        cwd = await self._git[spec.repository].worktree(ticket.lower(), _branch(ticket))
        transcript = self._root / "transcripts" / f"{session.session_id}.jsonl"
        await asyncio.to_thread(
            write_transcript, transcript, session_transcript(session, self._now)
        )
        base = {
            "session_id": session.session_id,
            "cwd": str(cwd),
            "transcript_path": str(transcript),
        }
        events: list[dict[str, object]] = [
            {"hook_event_name": "SessionStart", "source": "startup"},
            {"hook_event_name": "UserPromptSubmit", "prompt": session.prompt},
        ]
        for at, (tool, target) in enumerate(session.tools):
            call = {"tool_name": tool, "tool_input": tool_input(tool, target, cwd)}
            call["tool_use_id"] = f"{session.session_id}-{at}"
            events += [{"hook_event_name": "PreToolUse", **call}]
            events += [{"hook_event_name": "PostToolUse", **call}]
        if session.ended:
            events += [{"hook_event_name": "Stop"}, {"hook_event_name": "SessionEnd"}]
        for event in events:
            await run_hook(hook, {**base, **event})

    async def _capture_screens(self) -> None:
        title, images = CAPTURED
        spec = next(t for t in DEMO_TICKETS if t.title == title)
        ticket = self._ticket(title)
        tree = await self._git[spec.repository].tree(self._heads[title])
        folder = self._d.screens.folder_of(spec.repository, ticket, tree)
        for at, image in enumerate(images):
            shade = (24 + at * 16, 26 + at * 16, 32 + at * 16)
            await asyncio.to_thread(write_png, folder / image, 1280, 800, shade)
        await self._d.screens.record(ticket, tree, list(images), by=_BUILDER)


def _number(ticket_id: str) -> int:
    return int(ticket_id.rsplit("-", 1)[1])


def demo_root(state_dir: Path) -> Path:
    """Where the demo keeps its repositories and transcripts."""
    return state_dir / "demo"


def load_time() -> float:
    """Now, in seconds: the demo's history is dated back from the moment it loads."""
    return datetime.now(UTC).timestamp()
