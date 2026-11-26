"""Starting a check and answering what is known of the checks of a ticket."""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from code_factory.checks.models import (
    FIX_CHECK_REQUEST,
    NO_VERDICT_CODES,
    CheckRecord,
    CheckRun,
    ChecksView,
    Containment,
    RunState,
    Scope,
    StepRun,
    Verdict,
    ViewState,
)
from code_factory.checks.rules import failed_step, log_tail, verdict_for
from code_factory.checks.service.concluding import ConcludeMixin
from code_factory.checks.service.config import RunConfig, run_config
from code_factory.platform.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from code_factory.tickets.models import Ticket, TicketFilter

logger = logging.getLogger(__name__)
NO_SUCH_TICKET = "no such ticket"
NO_BRANCH = "the ticket has no branch"
NO_COMMIT = "the ticket's branch holds no commit"
RECORDS_READ = 50
_STATES = {
    Verdict.PASSED: ViewState.PASSED,
    Verdict.FAILED: ViewState.FAILED,
    Verdict.NO_VERDICT: ViewState.NO_VERDICT,
}


def _code(data: Mapping[str, Any]) -> int | None:
    code = data.get("exit_code")
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def _record(ticket_id: str, at: datetime, data: Mapping[str, Any]) -> CheckRecord:
    return CheckRecord(
        ticket_id=ticket_id,
        at=at,
        commit=str(data.get("commit", "")),
        exit_code=_code(data),
        tree=str(data.get("tree", "")),
        tree_id=str(data.get("tree_id", "")),
        log=str(data.get("log", "")),
        reason=str(data.get("reason", "")),
    )


class QueryMixin(ConcludeMixin):
    """Start a check; read the newest verdicts, logs and runs."""

    async def _ticket(self, ticket_id: str) -> Ticket:
        try:
            return await self._deps.tickets.get(ticket_id)
        except NotFoundError:
            raise NotFoundError(NO_SUCH_TICKET) from None

    async def _config(self, repository: str) -> RunConfig:
        return run_config(await self._deps.settings.load(await self._root(repository)))

    async def _insert(
        self, repository: str, subject: str, commit: str, details: tuple[Scope, Containment, str]
    ) -> CheckRun | None:
        scope, contained, by = details
        now = self._now()
        values = {
            "repository": repository,
            "subject": subject,
            "scope": scope.value,
            "commit": commit,
            "tree_id": await self._deps.git.tree_id(repository, commit),
            "state": RunState.QUEUED.value,
            "contained": contained.value,
            "owner": self._owner,
            "requested_by": by,
            "queued_at": now,
            "beat_at": now,
        }
        async with self._db() as store:
            return await store.runs.insert(values)

    async def start(
        self,
        ticket_id: str,
        scope: Scope = Scope.REACHED,
        by: str = "board",
        head: str | None = None,
    ) -> int:
        """Queue a run of the checks on the ticket's head (its branch's tip by default).

        The id of the run. A run already queued or running for the ticket is a `ConflictError`:
        the partial unique index decides it, not a read before the write.
        """
        ticket = await self._ticket(ticket_id)
        config = await self._config(ticket.repository)
        config.command(scope)
        if not ticket.branch:
            raise BadRequestError(NO_BRANCH)
        commit = head or (await self._deps.git.branch_state(ticket.repository, ticket.branch)).tip
        if not commit:
            raise BadRequestError(NO_COMMIT)
        row = await self._insert(
            ticket.repository, ticket.id, commit, (scope, config.containment(), by)
        )
        if row is None:
            msg = "checks are already running for this ticket"
            raise ConflictError(msg)
        self._enqueue(row.id)
        return row.id

    async def queue_head(
        self, ticket_id: str, head: str, by: str = "board", *, review_fix: bool = False
    ) -> int | None:
        """Queue required checks, or a configured fast check for a review fix first."""
        ticket = await self._ticket(ticket_id)
        config = await self._config(ticket.repository)
        if config.commands[Scope.REACHED] is None:
            return None
        if await self.verdict(ticket.repository, ticket.id, head) != "missing":
            return None
        scope = Scope.REACHED
        if review_fix and config.commands[Scope.FAST] is not None:
            if await self._fast_recorded(ticket.id, head):
                return None
            scope, by = Scope.FAST, FIX_CHECK_REQUEST
        try:
            return await self.start(ticket.id, scope=scope, by=by, head=head)
        except ConflictError:
            return None

    async def _fast_recorded(self, ticket: str, head: str) -> bool:
        return any(
            record.data.get("scope") == Scope.FAST
            and record.data.get("commit") == head
            and record.data.get("outcome") != "killed"
            and (code := _code(record.data)) is not None
            and code not in NO_VERDICT_CODES
            for record in await self._newest_records(ticket)
        )

    def _enqueue(self, check_id: int) -> None:
        """Wake the supervisor with the id; with no supervisor `run_now` executes it."""
        if self._group is None or check_id in self._known:
            return
        try:
            self._queue.put_nowait(check_id)
        except Exception:  # noqa: BLE001  # a full queue leaves the row queued: the keeper picks it up
            logger.warning("the checks queue is full; run %s waits for the keeper", check_id)
            return
        self._known.add(check_id)

    async def _newest_records(self, ticket_id: str, limit: int = RECORDS_READ) -> list[Any]:
        page = await self._deps.activity.list_activity(
            ticket_id, kinds=["checks"], limit=limit, newest_first=True
        )
        return page.items

    async def get(self, check_id: int) -> CheckRun:
        """The run `check_id`; `NotFoundError` when there is none."""
        return await self._row(check_id)

    async def recent_runs(self, limit: int = 20, subject: str | None = None) -> list[CheckRun]:
        """The newest runs, optionally of one subject (`CF-n` or `main`)."""
        async with self._db() as store:
            return await store.runs.recent(limit, subject)

    async def read_log(self, log: str) -> str | None:
        """The text of a log a `checks` record names; None for any name that is not one of ours."""
        path = await self._logs.within_any(log)
        return None if path is None else await self._logs.text_of(path)

    async def log_chunk(self, check_id: int, offset: int, size: int = 65536) -> tuple[str, int]:
        """What a run's log holds from `offset`, and the next offset; empty before it exists."""
        row = await self._row(check_id)
        path = await self._logs.within(row.repository, row.subject, row.log_path)
        if path is None:
            return "", offset
        text, _, following = await self._logs.page(path, offset, size)
        return text, following

    async def latest_verdicts(self, ids: Sequence[str]) -> dict[str, CheckRecord]:
        """The newest `checks` record of each ticket that has one."""
        found: dict[str, CheckRecord] = {}
        for ticket_id in ids:
            try:
                newest = await self._newest_records(ticket_id, 1)
            except NotFoundError:
                continue
            if newest:
                found[ticket_id] = _record(ticket_id, newest[0].at, newest[0].data)
        return found

    async def records_of(self, ids: Sequence[str]) -> dict[str, list[CheckRecord]]:
        """Each ticket's `checks` records, oldest first, in one read; none: the ticket is absent."""
        found = await self._deps.activity.records_of(list(ids), "checks")
        return {t: [_record(t, item.at, item.data) for item in items] for t, items in found.items()}

    async def records(self, repository: str, ticket_ids: Sequence[str]) -> list[CheckRecord]:
        """Every `checks` record of the tickets of `repository` among `ticket_ids`, oldest first."""
        found: list[CheckRecord] = []
        for ticket_id in ticket_ids:
            ticket = await self._ticket(ticket_id)
            if ticket.repository != repository:
                continue
            found.extend(
                _record(ticket_id, item.at, item.data)
                for item in await self._newest_records(ticket_id, 100)
                if item.data.get("scope") != Scope.FAST
            )
        return sorted(found, key=lambda record: record.at)

    async def step_runs(self, newest: int | None = None) -> list[StepRun]:
        """What each recent `checks` record says of its steps, newest first."""
        runs: list[StepRun] = []
        for ticket in await self._deps.tickets.list(TicketFilter(archived=None)):
            for item in await self._newest_records(ticket.id, newest or 100):
                data = item.data
                runs.append(
                    StepRun(
                        ticket_id=ticket.id,
                        at=item.at,
                        seconds=dict(data.get("seconds") or {}),
                        states=dict(data.get("steps") or {}),
                        retried=list(data.get("retried") or []),
                        lock_waits=dict(data.get("lock_waits") or {}),
                        slept=data.get("slept") is True,
                    )
                )
        runs.sort(key=lambda run: run.at, reverse=True)
        return runs if newest is None else runs[:newest]

    async def running(self, ids: Sequence[str]) -> set[str]:
        """The tickets among `ids` that have a queued or running check."""
        async with self._db() as store:
            active = await store.runs.active()
        return {row.subject for row in active} & set(ids)

    async def configured(self, repository: str) -> bool:
        """Whether the repository has a `[checks] command`."""
        return (await self._config(repository)).commands[Scope.REACHED] is not None

    async def log_tail(self, ticket_id: str, lines: int = 40) -> str:
        """The last lines of the newest failing check's log; empty on a pass or no record."""
        ticket = await self._ticket(ticket_id)
        newest = await self._newest_records(ticket_id, 1)
        if not newest or _code(newest[0].data) in {0, None}:
            return ""
        path = await self._logs.within(ticket.repository, ticket.id, str(newest[0].data.get("log")))
        text = None if path is None else await self._logs.text_of(path)
        return "" if text is None else log_tail(text, lines)

    async def verdict(self, repository: str, ticket_id: str, head: str) -> str:
        """`passed`, `failed` or `missing` for `head`, on the tree it names."""
        tree_id = await self._deps.git.tree_id(repository, head)
        items = await self._newest_records(ticket_id)
        return verdict_for([item.data for item in items], head, tree_id)

    async def latest(
        self, ticket_id: str, log_offset: int = 0, log_chars: int = 4000
    ) -> ChecksView:
        """The newest run of the ticket and a page of its log."""
        ticket = await self._ticket(ticket_id)
        async with self._db() as store:
            row = await store.runs.latest(ticket.repository, ticket.id)
        newest = await self._newest_records(ticket.id, RECORDS_READ)
        view = await self._view(ticket, row, newest)
        if view.state is ViewState.NONE:
            return view
        return await self._paged(ticket, view, log_offset, log_chars)

    async def _view(self, ticket: Ticket, row: CheckRun | None, records: list[Any]) -> ChecksView:
        """The state, commit, code and reasons of the newer of the row and the record."""
        newest = records[0] if records else None
        ended = None if row is None else row.finished_at
        if row is not None and (
            newest is None
            or row.state in {RunState.QUEUED, RunState.RUNNING}
            or (ended is not None and ended >= newest.at)
        ):
            commit, code, log = row.commit, row.exit_code, row.log_path
            if row.state is RunState.LOST:
                state = ViewState.NO_VERDICT
            else:
                state = ViewState(row.state.value) if row.verdict is None else _STATES[row.verdict]
            at, check_id = row.finished_at, row.id
        elif newest is not None:
            commit, code, log = (
                str(newest.data.get("commit", "")),
                _code(newest.data),
                str(newest.data.get("log", "")),
            )
            state = (
                ViewState.PASSED
                if code == 0
                else (
                    ViewState.NO_VERDICT if self._deps.stages.no_verdict(code) else ViewState.FAILED
                )
                if code is not None
                else ViewState.NO_VERDICT
            )
            at, check_id = newest.at, None
        else:
            return ChecksView(state=ViewState.NONE)
        record = next((r.data for r in records if r.data.get("commit") == commit), {})
        steps = record.get("steps") or {}
        tip = ""
        if ticket.branch:
            tip = (await self._deps.git.branch_state(ticket.repository, ticket.branch)).tip
        return ChecksView(
            state=state,
            check_id=check_id,
            commit=commit,
            head_current=bool(tip) and tip == commit,
            exit_code=code,
            failed_step=failed_step(list(steps.items())) if isinstance(steps, dict) else "",
            reason=str(record.get("reason", "")),
            finished_at=at,
            log_tail=log,
        )

    async def _paged(self, ticket: Ticket, view: ChecksView, offset: int, chars: int) -> ChecksView:
        """`view` with a page of its log: only a log of this ticket right in the logs folder."""
        path = await self._logs.within(ticket.repository, ticket.id, view.log_tail)
        if path is None:
            return view.model_copy(update={"log_tail": "", "log_offset": offset})
        text, size, following = await self._logs.page(path, max(offset, 0), max(chars, 0))
        return view.model_copy(
            update={
                "log_tail": text,
                "log_offset": max(offset, 0),
                "log_size": size,
                "next_offset": following,
            }
        )
