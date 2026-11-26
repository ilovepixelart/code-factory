"""Pushing what waits and answering it by its reply link, through the app with the sign-in on."""

import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from app_lifespan import IDLE_MODULES, running_lifespan
from code_factory.app import create_app
from code_factory.inbox.service import InboxService
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import NotFoundError
from code_factory.push.models import Message, Target
from code_factory.push.service import PushService
from code_factory.runs.models import PermissionRequest
from code_factory.runs.repository.permissions import PermissionRepository
from code_factory.runs.service import PermissionService
from code_factory.talk.service import TalkService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService

BOARD = "http://localhost"
REFUSAL = "this link was used, has expired or is not known"
REPLY = re.compile(r"http://localhost/reply/([0-9a-f]{64})")


@dataclass
class Recorder:
    """A delivery that records each message and answers `problem` (None: taken)."""

    problem: str | None = None
    sent: list[tuple[str, str, str]] = field(default_factory=list)

    async def deliver(self, target: Target, message: Message, link: str, reply: str) -> str | None:
        del target
        if self.problem is None:
            self.sent.append((message.text, link, reply))
        return self.problem


@dataclass
class Board:
    app: FastAPI
    client: httpx.AsyncClient
    push: PushService
    recorder: Recorder
    clock: list[datetime]
    ticket: str


@pytest.fixture
async def board(settings: Settings, connection: AsyncConnection) -> AsyncGenerator[Board]:
    sessions = async_sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    app = create_app(settings, sessions, modules=IDLE_MODULES)
    async with (
        running_lifespan(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BOARD) as client,
    ):
        services = app.state.services
        ticket = await services.get(TicketService).create(
            NewTicket(repository="sample", title="Pick a palette"), by="owner"
        )
        await services.get(TalkService).ask(ticket.id, "Which colour?", [], by="agent")
        clock = [datetime.now(UTC)]
        async with UnitOfWork(sessions)() as session:
            await PermissionRepository(session).add_request(
                PermissionRequest(
                    id="aaaaaaaaaaaa", repository="sample", ticket_key=ticket.id, tool="Bash",
                    summary="npm test", kind="Bash(npm *)", requested_at=clock[0],
                )
            )  # fmt: skip
        recorder = Recorder()
        push = PushService(
            UnitOfWork(sessions),
            services.get(InboxService),
            services.get(PermissionService),
            services.get(TalkService),
            recorder,
            lambda: clock[0],
        )
        await push.set_target("webhook", "https://push.example/hook")
        yield Board(app, client, push, recorder, clock, str(ticket.id))


def _token(board: Board, kind: str) -> str:
    [reply] = [r for text, _, r in board.recorder.sent if kind in text]
    found = REPLY.fullmatch(reply)
    assert found is not None
    return str(found.group(1))


async def test_each_waiting_item_is_sent_once_with_its_link(board: Board) -> None:
    await board.push.push_once(BOARD)
    await board.push.push_once(BOARD)

    texts = [(text, link) for text, link, _ in board.recorder.sent]
    assert texts == [
        (f"{board.ticket}: a question waits for your answer",
         f"{BOARD}/inbox#question-sample-{board.ticket}--0"),
        (f"{board.ticket}: an agent asks permission", f"{BOARD}/inbox#perm-aaaaaaaaaaaa"),
    ]  # fmt: skip


async def test_a_permission_link_reads_without_the_sign_in_and_answers_once(board: Board) -> None:
    await board.push.push_once(BOARD)
    path = f"/api/reply/{_token(board, 'permission')}"

    read = await board.client.get(path)
    allowed = await board.client.post(path, json={"verdict": "allow"})
    again = await board.client.post(path, json={"verdict": "deny"})

    assert (read.status_code, read.json()["tool"], read.json()["summary"]) == (
        200,
        "Bash",
        "npm test",
    )
    assert allowed.json() == {"notice": "Allowed", "undo": None}
    assert (again.status_code, again.json()["detail"]) == (404, REFUSAL)
    assert (await board.client.get("/api/inbox")).status_code == 403


async def test_a_question_link_answers_the_question(board: Board) -> None:
    await board.push.push_once(BOARD)
    path = f"/api/reply/{_token(board, 'question')}"

    read = await board.client.get(path)
    empty = await board.client.post(path, json={"answer": " "})
    answered = await board.client.post(path, json={"answer": "Blue"})

    assert (read.json()["kind"], read.json()["text"]) == ("question", "Which colour?")
    assert (empty.status_code, empty.json()["detail"]) == (400, "pick a choice or write an answer")
    assert answered.json()["notice"] == "Answered"
    assert (await board.client.get(path)).status_code == 404


async def test_a_link_past_its_wait_says_the_one_refusal(board: Board) -> None:
    await board.push.push_once(BOARD)
    board.clock[0] += timedelta(seconds=541)

    given = _token(board, "permission")
    with pytest.raises(NotFoundError, match=REFUSAL):
        await board.push.read(given)


async def test_a_failed_delivery_shows_on_the_inbox_until_a_pass_fails_nothing(
    board: Board,
) -> None:
    board.recorder.problem = "HTTP 500"
    await board.push.push_once(BOARD)
    failing = await board.push.summary()
    board.recorder.problem = None
    await board.push.push_once(BOARD)

    assert failing is not None
    assert (failing.host, failing.failure and failing.failure.problem) == (
        "push.example",
        "HTTP 500",
    )
    assert await board.push.summary() == failing.model_copy(update={"failure": None})
    assert len(board.recorder.sent) == 2


async def test_a_path_that_is_not_a_whole_token_still_needs_the_sign_in(board: Board) -> None:
    paths = [f"/api/reply/{'a' * 63}", f"/api/reply/{'A' * 64}", f"/api/reply/{'a' * 65}",
             f"/api/reply/{'a' * 64}/more"]  # fmt: skip
    assert [(await board.client.get(p)).status_code for p in paths] == [403, 403, 403, 403]
