"""The permission requests of a run's tool calls: policy, reviewer, owner, and the owner's rules.

The hook of a run (or the codex client) calls `request` and waits for its answer. The board's
policy settles what it can, then the configured reviewer, then the owner, whose answer is a row
that any process may write: the waiter wakes on an in-process event and re-reads the row every
`poll_s` seconds, so an answer written by a second process reaches it too.
"""

import asyncio
import contextlib
import hashlib
import json
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import anyio

from code_factory.agents.service import StartKit
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.runs.adapters.reviewer import ask_reviewer
from code_factory.runs.models import Decision, PermissionRequest, Review, Run
from code_factory.runs.ports import Config
from code_factory.runs.repository import PermissionRepository, RunRepository
from code_factory.runs.rules.hook_output import (
    OWNER_DENIED,
    RETRY_WORDS,
    REVIEWER_DENIED,
    hook_output,
)
from code_factory.runs.rules.reviews import review_verdict, settled_verdict, still_reviewed
from code_factory.runs.service.base import utc_now

WAIT_S = 540
POLL_S = 2.0
KEEP_DECISIONS = timedelta(days=90)
REVIEW_INPUT_LIMIT = 65_536
CLEANUP_S = 5.0
RECENT_DECISIONS = 20
ESCALATE_AFTER = 3  # policy refusals in a row before the owner is asked

STOPPED_WAITING = "the agent stopped waiting for this answer"
ALREADY_ANSWERED = "this request is already answered"
WAITED_TOO_LONG = (
    "this request waited longer than 9 minutes, so its agent no longer waits for an answer"
)
NOT_SUGGESTED = "that is not a suggested rule"
STANDING = "a standing rule of the owner"
SANDBOXED = "a command inside the run's sandbox"

Reviewer = Callable[[str, Path, str], Awaitable[tuple[bool, str] | None]]
Output = dict[str, Any]
DecidedBy = Literal["policy", "reviewer", "owner"]


class PermissionService:
    """Requests, answers and standing rules."""

    kit = StartKit()

    def __init__(
        self,
        uow: UnitOfWork,
        config: Config,
        *,
        clock: Callable[[], datetime] = utc_now,
        reviewer: Reviewer = ask_reviewer,
        poll_s: float = POLL_S,
    ) -> None:
        self._uow = uow
        self._config = config
        self._clock = clock
        self._reviewer = reviewer
        self._poll_s = poll_s
        self._waiters: dict[str, asyncio.Event] = {}

    async def request(
        self, run_id: str, payload: dict[str, Any], wait: float = WAIT_S, *, sandboxed: bool = False
    ) -> Output:
        """The hook output for one tool call of a run; `NotFoundError("no such run")`.

        Policy first (a refusal in a row of three goes to the owner with its words), then the
        owner's standing rules, then the reviewer unless the request carries a note, then the
        owner, who is waited for at most `wait` seconds. A shell command of a run started inside
        the sandbox (`sandboxed`) is allowed by the policy when the repository names no reviewer:
        the sandbox holds it to the tree and denies every host.
        """
        run = await self._run(run_id)
        tool = str(payload.get("tool_name", ""))
        call = payload.get("tool_input", {})
        session = str(payload.get("session_id", ""))
        settled, note = await self._by_policy(run, tool, call, sandboxed=sandboxed)
        if settled is not None:
            return settled
        if note == "":
            earlier = await self._by_rule(run, tool, call)
            if earlier is None:
                earlier = await self._by_reviewer(run, tool, call, session)
            if earlier is not None:
                return earlier
        return await self._by_owner(run, tool, call, note, wait)

    async def _run(self, run_id: str) -> Run:
        async with self._uow() as session:
            run = await RunRepository(session).get(run_id)
        if run is None:
            msg = "no such run"
            raise NotFoundError(msg)
        return run

    async def _record(
        self, run: Run, tool: str, *, allow: bool, by: DecidedBy, reason: str = ""
    ) -> None:
        decision = Decision(
            at=self._clock(),
            repository=run.repository,
            ticket_key=run.ticket_key,
            tool=tool,
            decision="allow" if allow else "deny",
            by=by,
            reason=reason,
        )
        async with self._uow() as session:
            await PermissionRepository(session).add_decision(decision)

    async def record_decision(
        self,
        run_id: str,
        tool: str,
        *,
        allow: bool,
        by: DecidedBy,
        reason: str = "",
    ) -> None:
        """Record a decision a caller made on the run's ticket; `NotFoundError("no such run")`."""
        await self._record(await self._run(run_id), tool, allow=allow, by=by, reason=reason)

    async def _by_policy(
        self, run: Run, tool: str, call: object, *, sandboxed: bool
    ) -> tuple[Output | None, str]:
        main = str(await self._config.root(run.repository))
        settled = self.kit.routine(tool, call, main, run.worktree, run.ticket_key)
        if settled is None and sandboxed and tool == "Bash":
            settings = await self._config.settings(run.repository)
            settled = (True, SANDBOXED) if settings.permission_reviewer is None else None
        if settled is None:
            return None, ""
        allow, words = settled
        if allow:
            await self._record(run, tool, allow=True, by="policy", reason=words)
            return hook_output(allow=True), ""
        async with self._uow() as session:
            recent = await PermissionRepository(session).latest_decisions(
                run.repository, run.ticket_key, ESCALATE_AFTER
            )
        in_a_row = self.kit.refused_in_a_row([d.model_dump() for d in recent])
        if in_a_row >= ESCALATE_AFTER:
            return None, self.kit.escalation(in_a_row, words)
        await self._record(run, tool, allow=False, by="policy", reason=words)
        return hook_output(allow=False, message=words), ""

    async def _by_rule(self, run: Run, tool: str, call: object) -> Output | None:
        kind = self.kit.request_kind(tool, call)
        if kind is None or kind not in await self.rules():
            return None
        await self._record(run, tool, allow=True, by="owner", reason=STANDING)
        return hook_output(allow=True)

    async def _by_reviewer(
        self, run: Run, tool: str, call: object, session_id: str
    ) -> Output | None:
        settings = await self._config.settings(run.repository)
        if settings.permission_reviewer is None:
            return None
        limit = settings.permission_reviewer_limit
        asked = json.dumps(
            {"tool_name": tool, "tool_input": call, "session_id": session_id,
             "ticket": run.ticket_key, "cwd": run.worktree},
            ensure_ascii=False,
        )  # fmt: skip
        async with self._uow() as session:
            earlier = await PermissionRepository(session).review_verdicts(session_id)
        if len(asked.encode()) > REVIEW_INPUT_LIMIT or not still_reviewed(earlier, limit):
            return None
        root = await self._config.root(run.repository)
        said = await self._reviewer(settings.permission_reviewer, root, asked)
        verdict, reason = review_verdict(said)
        review = Review(
            at=self._clock(),
            session_id=session_id,
            ticket_key=run.ticket_key,
            tool=tool,
            summary=self.kit.summary(tool, call),
            input_sha256=hashlib.sha256(asked.encode()).hexdigest(),
            verdict=verdict,
        )
        async with self._uow() as session:
            repo = PermissionRepository(session)
            await repo.record_review(review)
            before = (await repo.review_verdicts(session_id))[:-1]  # the review above is the last
        verdict = settled_verdict(verdict, still_open=still_reviewed(before, limit))
        if verdict == "owner":
            return None
        await self._record(run, tool, allow=verdict == "allow", by="reviewer", reason=reason)
        if verdict == "allow":
            return hook_output(allow=True)
        return hook_output(allow=False, message=REVIEWER_DENIED + reason)

    async def _by_owner(self, run: Run, tool: str, call: object, note: str, wait: float) -> Output:
        asked = PermissionRequest(
            id=secrets.token_hex(6),
            run_id=run.id,
            repository=run.repository,
            ticket_key=run.ticket_key,
            tool=tool,
            summary=self.kit.summary(tool, call),
            kind=self.kit.request_kind(tool, call),
            note=note,
            requested_at=self._clock(),
        )
        async with self._uow() as session:
            await PermissionRepository(session).add_request(asked)
        event = self._waiters[asked.id] = asyncio.Event()
        try:
            verdict = await self._answer_of(asked.id, event, wait)
        finally:
            self._waiters.pop(asked.id, None)
            await self._withdraw(asked.id)
        if verdict is None:
            return hook_output(allow=False, message=RETRY_WORDS)
        if verdict == "allow":
            return hook_output(allow=True)
        return hook_output(allow=False, message=OWNER_DENIED, interrupt=True)

    async def _answer_of(self, request_id: str, event: asyncio.Event, wait: float) -> str | None:
        try:
            async with asyncio.timeout(wait):
                while True:
                    event.clear()
                    async with self._uow() as session:
                        found = await PermissionRepository(session).get_request(request_id)
                    if found is None or found.status != "pending":
                        return None if found is None else found.verdict
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(event.wait(), self._poll_s)
        except TimeoutError:
            return None

    async def _withdraw(self, request_id: str) -> None:
        with anyio.CancelScope(shield=True):
            async with asyncio.timeout(CLEANUP_S), self._uow() as session:
                await PermissionRepository(session).withdraw(request_id)

    async def answer(self, request_id: str, *, allow: bool, by: str) -> PermissionRequest:
        """Record the owner's answer to a waiting request and wake its hook.

        `NotFoundError` for an unknown request or one its agent stopped waiting for,
        `ConflictError` for one already answered or older than the wait.
        """
        now = self._clock()
        refusal: tuple[type[Exception], str] | None = None
        async with self._uow() as session:
            repo = PermissionRepository(session)
            found = await repo.get_request(request_id)
            if found is None:
                msg = "no such permission request"
                raise NotFoundError(msg)
            refusal = _refusal(found)
            if refusal is None and found.requested_at < now - timedelta(seconds=WAIT_S):
                await repo.expire_before(now - timedelta(seconds=WAIT_S))
                refusal = (ConflictError, WAITED_TOO_LONG)
            if refusal is None and not await repo.answer(
                request_id, "allow" if allow else "deny", by, now
            ):
                refusal = (ConflictError, ALREADY_ANSWERED)
            if refusal is None:
                await repo.add_decision(
                    Decision(
                        at=now,
                        repository=found.repository,
                        ticket_key=found.ticket_key,
                        tool=found.tool,
                        decision="allow" if allow else "deny",
                        by="owner",
                    )
                )
        if refusal is not None:
            raise refusal[0](refusal[1])
        if (waiter := self._waiters.get(request_id)) is not None:
            waiter.set()
        return await self._request(request_id)

    async def _request(self, request_id: str) -> PermissionRequest:
        async with self._uow() as session:
            found = await PermissionRepository(session).get_request(request_id)
        assert found is not None  # noqa: S101  # the caller just wrote it
        return found

    async def expire(self, now: datetime) -> list[PermissionRequest]:
        """Expire every request older than the wait; the ones expired."""
        async with self._uow() as session:
            return await PermissionRepository(session).expire_before(
                now - timedelta(seconds=WAIT_S)
            )

    async def pending(self, now: datetime) -> list[PermissionRequest]:
        """The requests still waiting for the owner, oldest first; stale ones are expired first."""
        await self.expire(now)
        async with self._uow() as session:
            return await PermissionRepository(session).pending()

    async def withdraw_pending(self, before: datetime) -> int:
        """End the pending requests made before `before`: the waiters of a previous process."""
        async with self._uow() as session:
            return await PermissionRepository(session).withdraw_pending_before(before)

    async def _history(self) -> str:
        async with self._uow() as session:
            answered = await PermissionRepository(session).answered_history()
        return "\n".join(json.dumps({"kind": kind, "allowed": ok}) for kind, ok in answered)

    async def suggested(self) -> list[tuple[str, int]]:
        """The kinds the owner always allowed, often enough, that are not rules yet."""
        return self.kit.suggestions(await self._history(), await self.rules())

    async def answered_counts(self) -> dict[str, tuple[int, int]]:
        """Per kind of request: how many answers allowed it, and how many there were."""
        return self.kit.answer_history(await self._history())

    async def rules(self) -> list[str]:
        """The standing rules, in the order adopted."""
        async with self._uow() as session:
            return await PermissionRepository(session).rules()

    async def adopt_rule(self, kind: str) -> bool:
        """Adopt a suggested kind as a standing rule; `ConflictError` for any other kind."""
        if kind not in [suggested for suggested, _ in await self.suggested()]:
            raise ConflictError(NOT_SUGGESTED)
        async with self._uow() as session:
            return await PermissionRepository(session).adopt_rule(kind, self._clock())

    async def decisions(
        self, repository: str, ticket_key: str, count: int = RECENT_DECISIONS
    ) -> list[Decision]:
        """The latest decisions on the ticket's requests, oldest first."""
        async with self._uow() as session:
            return await PermissionRepository(session).latest_decisions(
                repository, ticket_key, count
            )

    async def prune(self, now: datetime) -> int:
        """Delete the decisions older than 90 days; how many."""
        async with self._uow() as session:
            return await PermissionRepository(session).prune_decisions(now - KEEP_DECISIONS)


def _refusal(found: PermissionRequest) -> tuple[type[Exception], str] | None:
    if found.status == "withdrawn":
        return NotFoundError, STOPPED_WAITING
    if found.status == "expired":
        return ConflictError, WAITED_TOO_LONG
    if found.status == "answered":
        return ConflictError, ALREADY_ANSWERED
    return None
