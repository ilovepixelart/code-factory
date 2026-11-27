"""Run an owner-configured expected-failure verifier before Build starts."""

import asyncio
import hashlib
import json
import logging
import shlex
import time
from pathlib import Path
from typing import cast

from code_factory.checks.adapters.environment import base_environment
from code_factory.checks.adapters.spec import publish_receipt
from code_factory.checks.models import Scope
from code_factory.checks.rules.spec import receipt_files
from code_factory.checks.service.base import SPEC_RECEIPT_BYTES
from code_factory.checks.service.upkeep import UpkeepMixin
from code_factory.platform.contained import Work
from code_factory.platform.errors import (
    BadRequestError,
    CodeFactoryError,
    ConflictError,
    UnavailableError,
)
from code_factory.platform.programs import find_program
from code_factory.tickets.models import Ticket

VERIFY_TIMEOUT_S = 240
SPEC_RETRY_S = 60
logger = logging.getLogger(__name__)


def _argv(text: str) -> tuple[Path, list[str]]:
    request = json.loads(text)
    if not isinstance(request, dict) or set(request) != {"argv"}:
        msg = "the spec request must contain an argv array"
        raise ValueError(msg)
    args = request["argv"]
    if (
        not isinstance(args, list)
        or not args
        or any(not isinstance(word, str) or "\0" in word for word in args)
    ):
        msg = "the spec request needs a nonempty argv array of strings"
        raise ValueError(msg)
    executable = Path(args[0])
    if not executable.is_absolute() or not executable.name:
        msg = "the spec verifier must be an absolute path to an owner-installed executable"
        raise ValueError(msg)
    return executable, cast("list[str]", args[1:])


def _receipt_line(log: str) -> str:
    possible = [line for line in log.splitlines() if line.lstrip().startswith("{")]
    if len(possible) == 1:
        return possible[0]
    msg = "the verifier must emit one single-line JSON receipt"
    raise ValueError(msg)


class SpecMixin(UpkeepMixin):
    """Expected failures requested from owner state gate agent launch."""

    async def _spec_request(self, ticket_id: str) -> tuple[Ticket, str] | None:
        """A request is optional and can only be supplied from owner-controlled board state."""
        git = self._deps.git
        try:
            request = await git.read_text_below(
                self._spec_state, f"spec-lock-requests/{ticket_id}.json", SPEC_RECEIPT_BYTES
            )
        except BadRequestError as error:
            msg = f"the spec request for {ticket_id} cannot be read: {error}"
            raise ConflictError(msg) from error
        if request is None:
            return None
        ticket = await self._ticket(ticket_id)
        config = await self._config(ticket.repository)
        if not config.sandboxed:
            msg = "the spec checks require the agent sandbox; enable it and retry Build"
            raise ConflictError(msg)
        if config.commands[Scope.REACHED] is None:
            msg = "the spec checks require [checks] command to enforce the receipt at merge"
            raise ConflictError(msg)
        return ticket, request

    async def prepare_build(self, ticket_id: str) -> bool:
        """Prove expected failures without holding a short-lived agent claim."""
        requested = await self._spec_request(ticket_id)
        if requested is None:
            return False
        ticket, request = requested
        git = self._deps.git
        head = (
            (await git.branch_state(ticket.repository, ticket.branch)).tip if ticket.branch else ""
        )
        if not head:
            msg = f"commit the spec tests on {ticket_id}'s branch before starting Build"
            raise ConflictError(msg)
        expected = hashlib.sha256(request.encode()).hexdigest()
        if await self._existing_spec(ticket.repository, ticket_id, head, expected):
            return False
        if self._group is not None:
            self._queue_spec(ticket, head, request, expected)
            msg = f"the expected-failure checks for {ticket_id} are running"
            raise ConflictError(msg)
        await self._seal_requested(ticket, head, request, expected)
        return True

    def _queue_spec(self, ticket: Ticket, head: str, request: str, expected: str) -> None:
        """Admit one proof per ticket without letting it block the follower's queue pass."""
        group = self._group
        if group is None or self._draining:
            msg = "the checks supervisor is stopping; retry Build once it resumes"
            raise ConflictError(msg)
        if ticket.id in self._spec_tasks:
            return
        failed = self._spec_failures.pop(ticket.id, None)
        if failed is not None and failed[:2] == (head, expected) and failed[3] > time.monotonic():
            self._spec_failures[ticket.id] = failed
            raise ConflictError(failed[2])
        if len(self._spec_tasks) >= self._admission_limit:
            msg = f"the expected-failure checks for {ticket.id} are waiting for a runner"
            raise ConflictError(msg)
        self._spec_tasks[ticket.id] = group.create_task(
            self._supervised_spec(ticket, head, request, expected), name=f"spec-{ticket.id}"
        )

    async def _supervised_spec(
        self, ticket: Ticket, head: str, request: str, expected: str
    ) -> None:
        reason = ""
        try:
            await self._seal_requested(ticket, head, request, expected)
        except CodeFactoryError as error:
            reason = str(error)
        except Exception:
            reason = f"the expected-failure checks for {ticket.id} could not run"
            logger.exception("%s", reason)
        finally:
            if reason:
                self._spec_failures[ticket.id] = (
                    head,
                    expected,
                    reason,
                    time.monotonic() + SPEC_RETRY_S,
                )
            self._spec_tasks.pop(ticket.id, None)

    async def _seal_requested(self, ticket: Ticket, head: str, request: str, expected: str) -> None:
        await self._policy.refresh()
        command = await self._spec_command(request)
        async with self._slots:
            if await self._existing_spec(ticket.repository, ticket.id, head, expected):
                return
            try:
                async with asyncio.timeout(VERIFY_TIMEOUT_S):
                    proof = await self._spec_proof(ticket.repository, ticket.id, head, command)
            except TimeoutError as error:
                msg = f"the expected-failure checks for {ticket.id} timed out"
                raise ConflictError(msg) from error
            proof["request_sha256"] = expected
            text = json.dumps(proof)
            if len(text.encode()) > SPEC_RECEIPT_BYTES:
                msg = f"the spec receipt for {ticket.id} exceeds {SPEC_RECEIPT_BYTES} bytes"
                raise ConflictError(msg)
            try:
                await publish_receipt(self._spec_state, f"{ticket.id}.json", text)
            except OSError as error:
                msg = f"the spec receipt for {ticket.id} could not be written in board state"
                raise UnavailableError(msg) from error

    async def verify_build(self, ticket_id: str, head: str) -> None:
        """Check the newest request and the actual Build head after the claim was taken."""
        requested = await self._spec_request(ticket_id)
        if requested is not None:
            ticket, request = requested
            expected = hashlib.sha256(request.encode()).hexdigest()
            if not await self._existing_spec(ticket.repository, ticket_id, head, expected):
                msg = f"the spec receipt for {ticket_id} is missing; retry Build"
                raise ConflictError(msg)

    async def _existing_spec(
        self, repository: str, ticket: str, head: str, request_digest: str
    ) -> bool:
        received = await self._deps.git.read_text_below(
            self._spec_state, f"spec-locks/{ticket}.json", SPEC_RECEIPT_BYTES
        )
        if received is None:
            return False
        refusal = await self._sealed_files_refusal(repository, ticket, head, received)
        if refusal is not None:
            raise ConflictError(refusal)
        if json.loads(received).get("request_sha256") != request_digest:
            msg = f"the spec request for {ticket} changed; review its receipt before retrying Build"
            raise ConflictError(msg)
        return True

    async def _spec_command(self, request: str) -> str:
        try:
            path, args = _argv(request)
        except ValueError as error:
            raise ConflictError(str(error)) from error
        program = await find_program(path.name, self._policy.places(), search_path=str(path.parent))
        if program is None:
            msg = "install the spec verifier outside the board and repositories, then retry Build"
            raise ConflictError(msg)
        return 'TMPDIR="$XDG_RUNTIME_DIR" ' + shlex.join([str(program), *args])

    async def _spec_proof(
        self, repository: str, ticket: str, head: str, command: str
    ) -> dict[str, object]:
        log = self._logs.path_for(repository, ticket, time.time_ns())
        env = await base_environment(self._policy.places())
        async with self._workspaces.snapshot(
            repository, head, ticket, setup=None, use_cache=False
        ) as work:
            before = await self._judge_tree.read(work.git_dir, work.path, env)
            if before.head != head or not before.tracked_clean:
                msg = f"the spec snapshot for {ticket} no longer matches its committed head"
                raise ConflictError(msg)
            code = await self._runner.run(
                Work.CHECKS,
                repository,
                command,
                work.path,
                log,
                VERIFY_TIMEOUT_S,
                require_sandbox=True,
            )
            if code != 0:
                msg = f"the expected-failure checks for {ticket} did not pass; see {log}"
                raise ConflictError(msg)
            after = await self._judge_tree.read(work.git_dir, work.path, env)
        if after.head != head or not after.tracked_clean:
            msg = f"the committed spec for {ticket} changed during the expected-failure checks"
            raise ConflictError(msg)
        git = self._deps.git
        try:
            output = await git.read_text_below(self._logs.folder, log.name, SPEC_RECEIPT_BYTES)
            text = _receipt_line(output or "")
            sealed, paths = receipt_files(text)
        except (BadRequestError, TypeError, ValueError) as error:
            msg = f"the spec verifier did not return a receipt for {ticket}; see {log}"
            raise ConflictError(msg) from error
        if sealed != head or await git.changed_files(repository, head, head, paths):
            msg = f"the spec receipt for {ticket} does not describe the committed snapshot"
            raise ConflictError(msg)
        return cast("dict[str, object]", json.loads(text))
