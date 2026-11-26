"""The small services: run requests, pruning, the capture hook and its redaction."""

import shlex
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.sessions.adapters import RedactionFile, SpoolReader
from code_factory.sessions.models import (
    HookSpec,
    PruneReport,
    Recurrence,
    ReportedTokens,
)
from code_factory.sessions.repository import (
    LedgerRepository,
    RunRequestRepository,
    ViewRepository,
)
from code_factory.sessions.rules import capture, repeats, telemetry
from code_factory.sessions.rules.redaction import redaction_text
from code_factory.sessions.service.ingest import LOCK_BUSY, LOCK_WAIT_MS

NOT_AN_OBJECT = "the telemetry export must be a JSON object"


class Upkeep:
    """What the service does besides ingesting and answering."""

    def __init__(
        self,
        uow: UnitOfWork,
        spool: SpoolReader,
        redaction: RedactionFile,
        state_dir: Path,
        lock_wait_ms: int = LOCK_WAIT_MS,
    ) -> None:
        self._uow = uow
        self._spool = spool
        self._redaction = redaction
        self._state_dir = state_dir
        self._lock_wait_ms = lock_wait_ms

    async def record_run_requests(self, run_id: str, export: object) -> int:
        """Keep the model requests a run's telemetry export reported; how many.

        Raises:
            BadRequestError: the export is not a JSON object.
        """
        if not isinstance(export, dict):
            raise BadRequestError(NOT_AN_OBJECT)
        found = telemetry.requests(export)
        if not found:
            return 0
        async with self._uow() as session:
            return await RunRequestRepository(session).add(run_id, found)

    async def run_reported_tokens(self, run_ids: Sequence[str]) -> dict[str, ReportedTokens]:
        """The tokens the named runs reported; a run with no requests is left out."""
        if not run_ids:
            return {}
        async with self._uow() as session:
            return await RunRequestRepository(session).totals(list(run_ids))

    async def forget_run(self, run_id: str) -> int:
        """Delete the requests a run reported; how many."""
        async with self._uow() as session:
            return await RunRequestRepository(session).forget(run_id)

    async def publish_redaction(
        self, patterns: Sequence[tuple[str, str]], references: Sequence[str]
    ) -> None:
        """Tell the capture hook what owner context to keep out of the spool."""
        await self._redaction.write(redaction_text(patterns, references))

    def capture_hook(self) -> HookSpec:
        """The command that records a hook event: this interpreter, isolated, on the hook file.

        It names the state folder itself, so an agent that does not inherit the board's
        environment still writes where the board reads.
        """
        command = shlex.join(
            [
                "/usr/bin/env",
                f"{capture.STATE_DIR_VARIABLE}={self._state_dir}",
                sys.executable,
                "-I",
                "-S",
                str(Path(capture.__file__).resolve()),
            ]
        )
        return HookSpec(command=command)

    async def recurring_failures(self, since: datetime) -> list[Recurrence]:
        """The check steps that failed the same way in several sessions since `since`."""
        async with self._uow() as session:
            rows = await LedgerRepository(session).output_rows(since)
        per_session: dict[str, list[repeats.Failure]] = {}
        for session_id, response, error in rows:
            found = repeats.failures(repeats.output_text(response, error))
            per_session.setdefault(session_id, []).extend(found)
        return repeats.recurring(list(per_session.items()))

    async def _lock(self, ledger: LedgerRepository) -> None:
        if not await ledger.lock(wait_ms=self._lock_wait_ms):
            raise UnavailableError(LOCK_BUSY)

    async def prune_spools(
        self, older_than_days: int, *, apply: bool, now: datetime
    ) -> PruneReport:
        """The spools last written before the cutoff, and with `apply` their rows and files.

        The events, rejects and views of those spools go in one transaction that holds the ingest
        lock; the files go after it, and a spool's progress only once its file is gone, so a file
        that cannot be removed is not taken in again.
        """
        cutoff = now - timedelta(days=older_than_days)
        names = await self._spool.names()
        stats = await self._spool.stats(names)
        old = {
            name: stats[name]
            for name in names
            if name in stats and stats[name][1] < cutoff.timestamp()
        }
        async with self._uow() as session:
            events, rejects = (
                await LedgerRepository(session).spool_counts(list(old)) if old else (0, 0)
            )
            requests = await RunRequestRepository(session).count_before(cutoff)
        report = PruneReport(
            len(old), events, rejects, sum(size for size, _ in old.values()), requests
        )
        if apply:
            await self._remove_rows_and_files(old, cutoff)
        return report

    async def _remove_rows_and_files(
        self, old: dict[str, tuple[int, float]], cutoff: datetime
    ) -> None:
        async with self._uow() as session:
            await RunRequestRepository(session).delete_before(cutoff)
        if not old:
            return
        async with self._uow() as session:
            ledger = LedgerRepository(session)
            await self._lock(ledger)
            await ledger.delete_spools(list(old))
            await ViewRepository(session).delete_orphans()
        gone = await self._spool.remove(old)
        async with self._uow() as session:
            ledger = LedgerRepository(session)
            await self._lock(ledger)
            # Lines an ingester read before the first transaction may have come back since.
            await ledger.delete_spools(gone)
            await ledger.delete_progress(gone)
            await ViewRepository(session).delete_orphans()
