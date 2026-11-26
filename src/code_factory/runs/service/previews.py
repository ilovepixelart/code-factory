"""A ticket's live preview: the repository's `[preview]` command run in the ticket's worktree.

The command runs in a group of its own, contained by the sandbox, with its port in
`CODE_FACTORY_PORT`. Its group is signalled only when this process holds it or `ps` shows the
process the board recorded; the command line carries the port marker so the check can tell it.
"""

import asyncio
import socket
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError, UnavailableError
from code_factory.platform.process import SHELL
from code_factory.runs.adapters import files
from code_factory.runs.adapters.processes import ProcessRegistry, Target
from code_factory.runs.models import PreviewRecord, PreviewStatus
from code_factory.runs.ports import PreviewSetup, RunPorts, TicketFacts
from code_factory.runs.repository import PreviewRepository
from code_factory.runs.rules.preview import preview_address
from code_factory.runs.service.base import utc_now
from code_factory.runs.service.reading import TICKET_PREFIX

NO_COMMAND = "no [preview] command in .code-factory/config.toml"
NO_PORT = "no free port for a preview"
_sockets = anyio.CapacityLimiter(1)


def _bind_free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


async def free_port() -> int:
    """A port nothing listens on, asked of the system in a thread."""
    try:
        return await anyio.to_thread.run_sync(_bind_free_port, limiter=_sockets)
    except OSError as error:
        raise UnavailableError(NO_PORT) from error


def marker(port: int) -> str:
    """The text of the preview's command line that names its port."""
    return f"CODE_FACTORY_PORT={port}"


def _target(record: PreviewRecord) -> Target:
    return Target(
        pid=record.pgid, started_at=record.pgid_started_at, exit_file=Path(marker(record.port))
    )


class PreviewService:
    """Starting, stopping and sweeping the previews of tickets."""

    def __init__(  # noqa: PLR0913  # the ports, the registry and the places of one service
        self,
        uow: UnitOfWork,
        ports: RunPorts,
        setup: PreviewSetup,
        registry: ProcessRegistry,
        *,
        state_dir: Path,
        board: str = "http://localhost",
        clock: Callable[[], datetime] = utc_now,
        pick_port: Callable[[], Awaitable[int]] = free_port,
    ) -> None:
        self._uow = uow
        self._ports = ports
        self._setup = setup
        self._registry = registry
        self._state_dir = state_dir
        self._board = board
        self._clock = clock
        self._pick_port = pick_port
        self._starting = asyncio.Lock()  # one start at a time: a start replaces the one before it

    def log_path(self, ticket_id: str) -> Path:
        """The preview's output."""
        return self._state_dir / "previews" / f"{ticket_id}.log"

    async def _live(self, number: int) -> PreviewRecord | None:
        """The ticket's preview when its process still runs; a dead one's row is removed."""
        async with self._uow() as session:
            repo = PreviewRepository(session)
            record = await repo.get(number)
            if record is None:
                return None
            if await self._registry.alive(_target(record)):
                return record
            await repo.delete(number, record.pgid)
        return None

    async def status(self, ticket_id: str) -> PreviewStatus:
        """The ticket's preview as its page shows it."""
        facts = await self._ports.tickets.facts(ticket_id)
        settings = await self._ports.config.settings(facts.repository)
        record = await self._live(facts.number)
        return PreviewStatus(
            configured=settings.preview_command is not None,
            running=record is not None,
            port=None if record is None else record.port,
            address=None if record is None else preview_address(self._board, record.port),
            started=None if record is None else record.started_at,
            idle_seconds=settings.preview_idle_s,
        )

    async def start(self, ticket_id: str, by: str) -> PreviewStatus:  # noqa: ARG002  # callers record who asked
        """Run the repository's preview command in the ticket's worktree, replacing a running one.

        `ConflictError` with the sentence when there is no command or no worktree;
        `UnavailableError` when the sandbox or a port cannot be had.
        """
        facts = await self._ports.tickets.facts(ticket_id)
        settings = await self._ports.config.settings(facts.repository)
        if settings.preview_command is None:
            raise ConflictError(NO_COMMAND)
        tree = await self._setup.tree_of(facts.repository, ticket_id)
        if tree is None:
            msg = f"{ticket_id} has no worktree to preview"
            raise ConflictError(msg)
        async with self._starting:
            await self.stop(ticket_id)
            await self._run(facts, tree, settings.preview_command)
        return await self.status(ticket_id)

    async def _run(self, facts: TicketFacts, tree: Path, command: str) -> None:
        port = await self._pick_port()
        script = f'CODE_FACTORY_PORT={port}; export CODE_FACTORY_PORT; {command}; exit "$?"'
        launch = await self._setup.contain((SHELL, "-c", script), tree, port)
        log = self.log_path(facts.id)
        await files.remove(log)
        spawned = await self._registry.spawn(launch.argv, env=launch.env, cwd=tree, log=log)
        async with self._uow() as session:
            await PreviewRepository(session).put(
                PreviewRecord(
                    ticket_id=facts.number,
                    repository=facts.repository,
                    pgid=spawned.pid,
                    pgid_started_at=spawned.started_at or self._clock(),
                    port=port,
                    started_at=self._clock(),
                )
            )

    async def stop(self, ticket_id: str) -> bool:
        """End the ticket's preview; `False` when it had none."""
        facts = await self._ports.tickets.facts(ticket_id)
        return await self._end(facts.number)

    async def _end(self, number: int) -> bool:
        async with self._uow() as session:
            record = await PreviewRepository(session).get(number)
        if record is None:
            return False
        await self._registry.kill(_target(record))
        async with self._uow() as session:
            await PreviewRepository(session).delete(number, record.pgid)
        return True

    async def running(self) -> list[PreviewRecord]:
        """The previews whose process runs; the rows of dead ones are removed."""
        async with self._uow() as session:
            recorded = await PreviewRepository(session).all()
        alive = [r for r in recorded if await self._live(r.ticket_id) is not None]
        return sorted(alive, key=lambda r: r.ticket_id)

    async def sweep(self, open_ticket_ids: set[str], now: datetime) -> list[str]:
        """Stop the previews of tickets no longer open and those running past their idle limit.

        The ids of the tickets whose preview was stopped.
        """
        stopped: list[str] = []
        for record in await self.running():
            ticket_id = f"{TICKET_PREFIX}{record.ticket_id}"
            settings = await self._ports.config.settings(record.repository)
            idle = settings.preview_idle_s
            gone = ticket_id not in open_ticket_ids
            late = idle is not None and (now - record.started_at).total_seconds() >= idle
            if (gone or late) and await self._end(record.ticket_id):
                stopped.append(ticket_id)
        return stopped
