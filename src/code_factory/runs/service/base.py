"""What every part of the runs service shares: the unit of work, the ports, the clock, the paths."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from code_factory.platform.db import UnitOfWork
from code_factory.runs.adapters.processes import ProcessRegistry
from code_factory.runs.models import Run
from code_factory.runs.ports import RunPorts

START_SLOTS = 4  # starts in flight at once: the model probe, the files, the spawn
STOP_PREFIX = "the run could not start: "


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


class ServiceBase:
    """The state of the run service's parts."""

    def __init__(
        self,
        uow: UnitOfWork,
        ports: RunPorts,
        registry: ProcessRegistry,
        *,
        state_dir: Path,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow = uow
        self._ports = ports
        self._registry = registry
        self._state_dir = state_dir
        self._clock = clock
        self._start_slots = asyncio.Semaphore(START_SLOTS)
        self._pass = asyncio.Lock()  # one collection pass at a time
        self._stopping: dict[str, asyncio.Lock] = {}

    @property
    def runs_dir(self) -> Path:
        """Where runs' logs, exit files and sandbox files are."""
        return self._state_dir / "runs"

    def log_path(self, run_id: str) -> Path:
        """The run's log, streamed by its process."""
        return self.runs_dir / f"{run_id}.log"

    def exit_path(self, run_id: str) -> Path:
        """The exit file its wrapper writes."""
        return self.runs_dir / f"{run_id}.exit"

    def patterns_path(self, run_id: str) -> Path:
        """The patterns its wrapper redacts its output with."""
        return self.runs_dir / f"{run_id}.patterns.json"

    def exit_file_of(self, run: Run) -> Path:
        """The exit file of a recorded run, from its log's place."""
        return Path(run.log).with_suffix(".exit") if run.log else self.exit_path(run.id)
