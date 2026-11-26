"""What every part of the agents service shares: the unit of work, the clock and the adapters."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from code_factory.agents.adapters.credentials import CredentialStore, KeyStore
from code_factory.agents.adapters.files import ClaudeAgentFiles, CodexLoginFile, RunLogReader
from code_factory.agents.adapters.probe import ModelProbe
from code_factory.agents.models.answers import RenameGuard
from code_factory.agents.models.connections import Status
from code_factory.agents.rules.login import codex_login, login_problem
from code_factory.platform.db import UnitOfWork


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


class Shared:
    """Dependencies of the service; a test injects a frozen clock and fakes."""

    def __init__(  # noqa: PLR0913  # the adapters of one service, all optional
        self,
        uow: UnitOfWork,
        *,
        clock: Callable[[], datetime] = utc_now,
        store: KeyStore | None = None,
        probe: ModelProbe | None = None,
        files: ClaudeAgentFiles | None = None,
        login: CodexLoginFile | None = None,
        logs: RunLogReader | None = None,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._store = store or CredentialStore()
        self._probe = probe or ModelProbe()
        self._files = files or ClaudeAgentFiles()
        self._login = login or CodexLoginFile()
        self._logs = logs or RunLogReader()
        self._guards: list[RenameGuard] = []
        self._check_locks: dict[str, asyncio.Lock] = {}
        self._checks_at_once = asyncio.Semaphore(2)

    async def _codex_catalog(self, connection: str) -> Status:
        path, text = await self._login.read()
        problem = login_problem(str(path), text)
        if problem is not None or text is None:
            return Status(name=connection, answers=False, problem=problem or "")
        return await self._probe.codex_status(connection, codex_login(text))
