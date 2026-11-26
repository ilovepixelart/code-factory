"""The push module's public API: `PushService`."""

import asyncio
import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlsplit

from code_factory.inbox.models import PushFailure, PushState
from code_factory.inbox.service import InboxService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from code_factory.push.models import Kept, Message, Target
from code_factory.push.repository import PushRepository
from code_factory.push.rules import (
    QUESTION_WAIT_S,
    REFUSAL,
    address_refusal,
    bad_reply,
    identity,
    messages,
    still_answers,
)
from code_factory.runs.service import PermissionService
from code_factory.talk.models import Reply
from code_factory.talk.service import TalkService

OWNER = "owner:owner"
TOKEN_BYTES = 32


class Delivery(Protocol):
    """Sends one message; the problem when it was not taken."""

    async def deliver(self, target: Target, message: Message, link: str, reply: str) -> str | None:
        """Deliver `message`, linking to `link`, with `reply` when it has one."""
        ...


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PushService:
    """Pushes what waits on the owner to the target and answers the reply links it sent."""

    def __init__(  # noqa: PLR0913, PLR0917  # its neighbours, the delivery and the clock
        self,
        uow: UnitOfWork,
        inbox: InboxService,
        permissions: PermissionService,
        talk: TalkService,
        delivery: Delivery,
        clock: Callable[[], datetime],
    ) -> None:
        self._uow = uow
        self._inbox = inbox
        self._permissions = permissions
        self._talk = talk
        self._delivery = delivery
        self._clock = clock

    async def set_target(self, format_: str, url: str) -> Target:
        """Push to `url` in `format_` (`ntfy` or `webhook`) from now on."""
        refusal = address_refusal(format_, url)
        if refusal is not None:
            raise BadRequestError(refusal)
        target = Target(format=format_, url=url)  # ty: ignore[invalid-argument-type]  # checked above
        async with self._uow() as session:
            repository = PushRepository(session)
            await repository.set_target(target, self._clock())
            await repository.clear_failure()
        return target

    async def clear_target(self) -> None:
        """Push nothing from now on."""
        async with self._uow() as session:
            await PushRepository(session).clear_target()

    async def summary(self) -> PushState | None:
        """What the Inbox says of pushing: None without a target, else its host and the failure."""
        async with self._uow() as session:
            repository = PushRepository(session)
            target, failure = await repository.target(), await repository.failure()
        if target is None:
            return None
        found = (
            None if failure is None else PushFailure(at=failure[0].timestamp(), problem=failure[1])
        )
        return PushState(host=urlsplit(target.url).hostname or "", failure=found)

    async def run(self, every_s: float, base_url: Callable[[], str]) -> None:
        """Pass every `every_s` seconds while the app runs, linking to the board at `base_url`."""
        while True:
            board = base_url()
            if board:
                await self.push_once(board)
            await asyncio.sleep(every_s)

    async def push_once(self, board: str) -> None:
        """Send each waiting item not sent yet; stop at the first failed delivery and record it.

        A digest is claimed before its delivery, so two boards on one database send it once.
        """
        async with self._uow() as session:
            target = await PushRepository(session).target()
        if target is None:
            return
        now = self._clock()
        page = await self._inbox.page()
        waiting = messages(page)
        async with self._uow() as session:
            repository = PushRepository(session)
            sent = await repository.keep_only_sent({m.digest for m in waiting})
            await repository.forget_before(now - timedelta(seconds=QUESTION_WAIT_S))
        for message in waiting:
            if message.digest in sent:
                continue
            problem = await self._send(target, message, board.rstrip("/"), now)
            if problem is not None:
                async with self._uow() as session:
                    await PushRepository(session).set_failure(now, problem)
                return
        async with self._uow() as session:
            await PushRepository(session).clear_failure()

    async def _send(
        self, target: Target, message: Message, board: str, now: datetime
    ) -> str | None:
        async with self._uow() as session:
            if not await PushRepository(session).claim(message.digest, now):
                return None
        reply = await self._mint(message, board, now)
        problem = await self._delivery.deliver(
            target, message, f"{board}/inbox#{message.anchor}", reply
        )
        if problem is not None:
            async with self._uow() as session:
                await PushRepository(session).unclaim(message.digest)
        return problem

    async def _mint(self, message: Message, board: str, now: datetime) -> str:
        if message.request is None and message.question is None:
            return ""
        token = secrets.token_hex(TOKEN_BYTES)
        kept = Kept(message.request or "", message.question or (), now.timestamp())
        async with self._uow() as session:
            await PushRepository(session).mint(_digest(token), kept, now)
        return f"{board}/reply/{token}"

    async def _kept(self, token: str) -> Kept:
        async with self._uow() as session:
            kept = await PushRepository(session).find(_digest(token))
        if kept is None or not still_answers(
            kept.request, kept.minted_at, self._clock().timestamp()
        ):
            raise NotFoundError(REFUSAL)
        return kept

    async def _waiting(self, kept: Kept) -> dict[str, Any]:
        """The item a token answers as it waits now, else the one refusal."""
        page = await self._inbox.page()
        if kept.request:
            found = (
                i for i in page["permissions"] if (i.get("request") or {}).get("id") == kept.request
            )
        else:
            found = (i for i in page["questions"] if identity("questions", i) == kept.question)
        item = next(found, None)
        if item is None:
            raise NotFoundError(REFUSAL)
        return item

    async def read(self, token: str) -> dict[str, Any]:
        """What a reply link waits on. Changes nothing: link scanners fetch links."""
        item = await self._waiting(await self._kept(token))
        ticket = item.get("ticket") or {}
        if item.get("request"):
            return {
                "ticket": ticket.get("id", ""),
                "title": ticket.get("title", ""),
                "tool": item["request"]["tool"],
                "summary": item["request"]["summary"],
                "at": item.get("since"),
            }
        question = item["question"]
        return {
            "kind": "question",
            "ticket": ticket.get("id", ""),
            "title": ticket.get("title", ""),
            **{
                key: question[key]
                for key in ("document", "index", "text", "topic", "choices", "several")
                if key in question
            },
        }

    async def press(self, token: str, verdict: str | None, choices: list[str], answer: str) -> str:
        """Answer what the link waits on as the Inbox does and spend the link; the notice."""
        kept = await self._kept(token)
        item = await self._waiting(kept)
        if kept.request:
            if verdict not in {"allow", "deny"}:
                raise BadRequestError("press allow or deny")
            await self._spend(token)
            try:
                await self._permissions.answer(kept.request, allow=verdict == "allow", by=OWNER)
            except NotFoundError, ConflictError:
                raise NotFoundError(REFUSAL) from None
            return "Allowed" if verdict == "allow" else "Denied"
        refusal = (
            "answer the question"
            if verdict is not None
            else bad_reply(item["question"], choices, answer)
        )
        if refusal is not None:
            raise BadRequestError(refusal)
        await self._spend(token)
        question = item["question"]
        try:
            await self._talk.answer_shown(
                item["ticket"]["id"], question["document"], question["index"], question["text"],
                Reply(choices=choices, text=answer), by=OWNER, channel="reply",
            )  # fmt: skip
        except NotFoundError, ConflictError, BadRequestError:
            raise NotFoundError(REFUSAL) from None
        return "Answered"

    async def _spend(self, token: str) -> None:
        async with self._uow() as session:
            if await PushRepository(session).spend(_digest(token)) is None:
                raise NotFoundError(REFUSAL)
