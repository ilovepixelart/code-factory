"""Helpers of the agents tests: a movable clock and a fake credential store."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from code_factory.agents.adapters.files import ClaudeAgentFiles, CodexLoginFile
from code_factory.agents.service import AgentService
from code_factory.platform.db import UnitOfWork

START = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


class Unfrozen:
    """The `frozen` of a rename guard whose writers need no holding off."""

    @asynccontextmanager
    async def frozen(self, _name: str) -> AsyncGenerator[None]:
        yield


class Clock:
    """A clock that moves only when a test says so."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def after(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class FakeStore:
    """A credential store over a dict; reads are recorded, values are never logged."""

    def __init__(self, keys: dict[str, str] | None = None) -> None:
        self.keys = keys or {}

    async def read(self, name: str) -> SecretStr | None:
        return SecretStr(self.keys[name]) if self.keys.get(name, "") != "" else None

    async def has(self, name: str) -> bool:
        return self.keys.get(name, "") != ""

    async def remove(self, name: str) -> bool:
        return self.keys.pop(name, None) is not None

    async def store(self, name: str) -> int:
        self.keys[name] = "stored"
        return 0


@pytest.fixture(name="clock")
def clock_fixture() -> Clock:
    return Clock()


@pytest.fixture(name="store")
def store_fixture() -> FakeStore:
    return FakeStore()


@pytest.fixture(name="agents")
def agents_fixture(uow: UnitOfWork, clock: Clock, store: FakeStore, tmp_path: Path) -> AgentService:
    return AgentService(
        uow,
        clock=clock,
        store=store,
        files=ClaudeAgentFiles(tmp_path / "claude"),
        login=CodexLoginFile(tmp_path / "codex"),
    )
