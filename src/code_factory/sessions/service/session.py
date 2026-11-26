"""`SessionService`: what agent sessions do, from the capture spool to the Sessions page."""

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from pathlib import Path

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError
from code_factory.platform.text import Paging
from code_factory.sessions.adapters import (
    CheckoutLocator,
    RedactionFile,
    SpoolReader,
    TranscriptReader,
)
from code_factory.sessions.models import (
    AtWork,
    HookSpec,
    IngestResult,
    JsonAnswer,
    PruneReport,
    Recurrence,
    ReportedTokens,
    SessionView,
    StateFilter,
)
from code_factory.sessions.repository import ListenConnection, channel_for
from code_factory.sessions.rules.stream import position
from code_factory.sessions.service.common import Clock, utc_now
from code_factory.sessions.service.ingest import (
    BATCH_LINES,
    LOCK_WAIT_MS,
    Ingester,
    IngestOptions,
)
from code_factory.sessions.service.rebuild import Rebuilder
from code_factory.sessions.service.stream import StreamHub, StreamTiming
from code_factory.sessions.service.upkeep import Upkeep
from code_factory.sessions.service.usage import KEPT_TRANSCRIPTS, UsageReader
from code_factory.sessions.service.views import DEFAULT_LAST, ViewReader

logger = logging.getLogger(__name__)

AFTER_REFUSED = "after must be an integer"
TICK_S = 0.25
MAINTENANCE_S = 60.0


class SessionService:
    """Records what every agent session does and answers who is working on what.

    A unit of work per call; no transaction is open across a file read.
    """

    def __init__(  # noqa: PLR0913  # its ports are what the module is built from
        self,
        uow: UnitOfWork,
        *,
        state_dir: Path,
        listen_dsn: str | None = None,
        clock: Clock = utc_now,
        timing: StreamTiming | None = None,
        spool: SpoolReader | None = None,
        locator: CheckoutLocator | None = None,
        transcripts: TranscriptReader | None = None,
        kept_transcripts: int = KEPT_TRANSCRIPTS,
        batch_lines: int = BATCH_LINES,
        lock_wait_ms: int = LOCK_WAIT_MS,
        schema: str = "public",
    ) -> None:
        self._clock = clock
        self._listen_dsn = listen_dsn
        self._spool = spool or SpoolReader(state_dir / "spool")
        self._locator = locator or CheckoutLocator()
        self._transcripts = transcripts or TranscriptReader()
        self._channel = channel_for(schema)
        self._ingest = Ingester(
            uow,
            self._spool,
            self._locator,
            options=IngestOptions(batch_lines, lock_wait_ms, self._channel),
        )
        self._rebuild = Rebuilder(uow, self._locator, self._ingest, lock_wait_ms)
        self._views = ViewReader(uow, clock)
        self._usage = UsageReader(uow, self._transcripts, kept=kept_transcripts)
        self._hub = StreamHub(uow, timing=timing)
        self._upkeep = Upkeep(uow, self._spool, RedactionFile(state_dir), state_dir, lock_wait_ms)

    async def list_sessions(
        self, paging: Paging | None, *, ended: bool = False, state: StateFilter | None = None
    ) -> JsonAnswer:
        """The Sessions list: every session unpaged, or one page of it."""
        return await self._views.list_sessions(paging, ended=ended, state=state)

    async def board_views(self, now: float | None = None) -> list[SessionView]:
        """The live sessions, in the order that draws attention."""
        return await self._views.board_views(now)

    async def subagents_at_work(
        self, now: float | None = None, *, fresh_only: bool = False
    ) -> list[AtWork]:
        """The running subagents of live sessions that work on a ticket."""
        return await self._views.subagents_at_work(now, fresh_only=fresh_only)

    async def timeline(self, session_id: str, last: int = DEFAULT_LAST) -> JsonAnswer:
        """One session and its timeline."""
        return await self._views.timeline(session_id, last)

    async def call(self, session_id: str, seq: int) -> JsonAnswer:
        """The input and output of one tool call."""
        return await self._views.call(session_id, seq)

    async def usage(self, session_ids: tuple[str, ...] = ()) -> dict[str, dict[str, object]]:
        """The tokens and cost of each named known session, or of every session."""
        return await self._usage.usage(session_ids)

    def event_stream(self, after: int, stop: asyncio.Event) -> AsyncIterator[str]:
        """The frames of every event past `after`, then each new one; ends when `stop` is set."""
        return self._hub.stream(after, stop)

    @property
    def open_streams(self) -> int:
        """How many event streams are open now."""
        return self._hub.open_streams

    @staticmethod
    def parse_position(after: str | None, last_event_id: str | None) -> int:
        """The `seq` a stream resumes after.

        Raises:
            BadRequestError: the value that applies is not an integer.
        """
        found = position(after, last_event_id)
        if found is None:
            raise BadRequestError(AFTER_REFUSED)
        return found

    async def record_run_requests(self, run_id: str, export: object) -> int:
        """Keep the model requests a run's telemetry export reported; how many."""
        return await self._upkeep.record_run_requests(run_id, export)

    async def run_reported_tokens(self, run_ids: Sequence[str]) -> dict[str, ReportedTokens]:
        """The tokens the named runs reported."""
        return await self._upkeep.run_reported_tokens(run_ids)

    async def forget_run(self, run_id: str) -> int:
        """Delete the requests a run reported."""
        return await self._upkeep.forget_run(run_id)

    async def ingest_once(self, *, wait: bool = False) -> IngestResult:
        """Take every new whole line of the spool into the ledger."""
        return await self._ingest.ingest_once(wait=wait)

    async def rebuild_views(self, *, batch: int = 500, stale_only: bool = False) -> int:
        """Derive every session's view again from its events."""
        return await self._rebuild.rebuild(batch=batch, stale_only=stale_only)

    async def prune_spools(self, older_than_days: int, *, apply: bool) -> PruneReport:
        """The spools last written before the cutoff, removed with their rows when `apply`."""
        return await self._upkeep.prune_spools(older_than_days, apply=apply, now=self._clock())

    async def publish_redaction(
        self, patterns: Sequence[tuple[str, str]], references: Sequence[str]
    ) -> None:
        """Tell the capture hook what owner context to keep out of the spool."""
        await self._upkeep.publish_redaction(patterns, references)

    def capture_hook(self) -> HookSpec:
        """The command that records a hook event."""
        return self._upkeep.capture_hook()

    async def recurring_failures(self, since: datetime) -> list[Recurrence]:
        """The check steps that failed the same way in several sessions since `since`."""
        return await self._upkeep.recurring_failures(since)

    async def run_ingest(self) -> None:
        """The background task that moves the spool into the ledger until cancelled."""
        checked = False
        while True:
            try:
                if not checked and await self._spool.names():
                    # Only once there is a spool: a process with none touches no table.
                    await self.rebuild_views(stale_only=True)
                    checked = True
                taken = await self.ingest_once()
            except Exception:
                logger.exception("an ingest pass of the session spool failed")
                taken = IngestResult()
            if not taken.lines:
                await asyncio.sleep(TICK_S)

    async def run_listen(self) -> None:
        """The background task that wakes the open streams on each notification."""
        if self._listen_dsn is None:
            return
        await ListenConnection(self._listen_dsn, self._channel, self._hub.wake).run()

    def maintain(self) -> None:
        """Drop the transcript totals past their bound and the checkout answers past their time."""
        self._usage.trim()
        self._locator.expire()

    async def run_maintenance(self) -> None:
        """The background task that drops what the caches no longer need."""
        while True:
            await asyncio.sleep(MAINTENANCE_S)
            self.maintain()

    async def shutdown(self) -> None:
        """End the open streams."""
        self._hub.shutdown()
