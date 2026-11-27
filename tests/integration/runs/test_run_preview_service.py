"""A ticket's live preview: start, replace, stop, the dead one's row, the sweep."""

import asyncio
import os
import signal
import socket
from collections.abc import Sequence
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError, UnavailableError
from code_factory.runs.adapters.processes import ProcessRegistry
from code_factory.runs.models import PreviewRecord
from code_factory.runs.ports import Launch, Settings, TicketFacts
from code_factory.runs.repository import PreviewRepository
from code_factory.runs.service.previews import PreviewService, free_port
from runs_fakes import Fakes
from runs_values import NOW, FakeClock, at

BOARD = "http://localhost:4100"


class FakeSetup:
    """The tree of a ticket and the contained launch: no sandbox, the plain shell."""

    def __init__(self, tree: Path) -> None:
        self.tree: Path | None = tree
        self.refusal: Exception | None = None
        self.contained: list[tuple[Sequence[str], Path, int]] = []

    async def tree_of(self, repository: str, ticket_id: str) -> Path | None:  # noqa: ARG002
        return self.tree

    async def contain(self, argv: Sequence[str], tree: Path, port: int) -> Launch:
        if self.refusal is not None:
            raise self.refusal
        self.contained.append((argv, tree, port))
        return Launch(argv=tuple(argv), env={"PATH": "/usr/bin:/bin"})


class Ports:
    """Distinct free ports, the way the service asks for them."""

    def __init__(self) -> None:
        self.next = 5001

    async def __call__(self) -> int:
        self.next += 1
        return self.next - 1


@pytest.fixture
def setup(tmp_path: Path) -> FakeSetup:
    tree = tmp_path / "tree"
    tree.mkdir()
    return FakeSetup(tree)


@pytest.fixture
def ports() -> Ports:
    return Ports()


@pytest.fixture
def previews(  # noqa: PLR0913, PLR0917  # the fixtures a preview service is made of
    uow: UnitOfWork,
    fakes: Fakes,
    setup: FakeSetup,
    registry: ProcessRegistry,
    tmp_path: Path,
    clock: FakeClock,
    ports: Ports,
) -> PreviewService:
    fakes.config.value = Settings(preview_command="sleep 30", preview_idle_s=60)
    return PreviewService(
        uow,
        fakes.ports,
        setup,
        registry,
        state_dir=tmp_path / "state",
        board=BOARD,
        clock=clock,
        pick_port=ports,
    )


async def test_a_repository_with_no_preview_command_is_not_configured(
    previews: PreviewService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.config.value = Settings()
    status = await previews.status(facts.id)
    assert (status.configured, status.running, status.port) == (False, False, None)


async def test_a_configured_ticket_with_no_preview_is_not_running(
    previews: PreviewService, facts: TicketFacts
) -> None:
    status = await previews.status(facts.id)
    assert (status.configured, status.running, status.idle_seconds) == (True, False, 60)


async def test_a_start_without_a_command_is_refused_with_the_config_sentence(
    previews: PreviewService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.config.value = Settings()
    with pytest.raises(
        ConflictError, match=r"^no \[preview\] command in .code-factory/config.toml$"
    ):
        await previews.start(facts.id)


async def test_a_start_without_a_worktree_is_refused_naming_the_ticket(
    previews: PreviewService, setup: FakeSetup, facts: TicketFacts
) -> None:
    setup.tree = None
    with pytest.raises(ConflictError, match=f"^{facts.id} has no worktree to preview$"):
        await previews.start(facts.id)


async def test_a_start_the_sandbox_refuses_leaves_no_preview(
    previews: PreviewService, setup: FakeSetup, facts: TicketFacts
) -> None:
    setup.refusal = UnavailableError("srt is not installed")
    with pytest.raises(UnavailableError, match="srt is not installed"):
        await previews.start(facts.id)
    assert await previews.running() == []


async def test_a_start_runs_the_command_in_the_tree_with_its_port(
    previews: PreviewService, fakes: Fakes, setup: FakeSetup, facts: TicketFacts, tmp_path: Path
) -> None:
    fakes.config.value = Settings(
        preview_command='echo "$CODE_FACTORY_PORT" > port.txt; pwd > where.txt; sleep 30'
    )
    status = await previews.start(facts.id)
    assert status.running is True
    assert status.port == 5001
    assert status.address == "http://127.0.0.1:4100/preview/5001"
    assert status.started == NOW
    assert setup.tree is not None
    for _ in range(100):
        if (setup.tree / "where.txt").exists():
            break
        await asyncio.sleep(0.05)
    assert (setup.tree / "port.txt").read_text().strip() == "5001"
    assert (setup.tree / "where.txt").read_text().strip() == str(setup.tree.resolve())
    assert (tmp_path / "state" / "previews" / f"{facts.id}.log").exists()
    await previews.stop(facts.id)


async def test_a_second_start_replaces_the_running_preview(
    previews: PreviewService,
    facts: TicketFacts,
    db_session: AsyncSession,
    registry: ProcessRegistry,
) -> None:
    first = await previews.start(facts.id)
    recorded = await PreviewRepository(db_session).get(facts.number)
    assert recorded is not None
    second = await previews.start(facts.id)
    assert (first.port, second.port) == (5001, 5002)
    for _ in range(100):
        if registry.returncode(recorded.pgid) is not None:
            break
        await asyncio.sleep(0.05)
    assert registry.returncode(recorded.pgid) == -signal.SIGKILL
    assert len(await previews.running()) == 1
    await previews.stop(facts.id)


async def test_a_stop_ends_the_whole_group_and_removes_the_preview(
    previews: PreviewService, fakes: Fakes, facts: TicketFacts, tmp_path: Path
) -> None:
    marker = tmp_path / "child.pid"
    fakes.config.value = Settings(
        preview_command=f"sleep 30 & echo $! > {marker}; wait", preview_idle_s=60
    )
    await previews.start(facts.id)
    for _ in range(100):
        if marker.exists() and marker.read_text().strip():
            break
        await asyncio.sleep(0.05)
    child = int(marker.read_text())
    assert await previews.stop(facts.id) is True
    await asyncio.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)  # the grandchild went with the group
    assert (await previews.status(facts.id)).running is False


async def test_stopping_a_ticket_with_no_preview_says_so(
    previews: PreviewService, facts: TicketFacts
) -> None:
    assert await previews.stop(facts.id) is False


async def test_a_preview_that_ended_by_itself_loses_its_row(
    previews: PreviewService, fakes: Fakes, facts: TicketFacts, registry: ProcessRegistry
) -> None:
    fakes.config.value = Settings(preview_command="exit 0", preview_idle_s=60)
    await previews.start(facts.id)
    await registry.reap_all()
    assert (await previews.status(facts.id)).running is False
    assert await previews.running() == []


async def test_a_recorded_group_nobody_can_vouch_for_is_never_signalled(
    previews: PreviewService, facts: TicketFacts, db_session: AsyncSession
) -> None:
    stranger = await asyncio.create_subprocess_exec("/bin/sleep", "30", start_new_session=True)
    try:
        await PreviewRepository(db_session).put(
            PreviewRecord(
                ticket_id=facts.number,
                repository="sample",
                pgid=stranger.pid,
                pgid_started_at=at(-3600),
                port=5009,
                started_at=at(0),
            )
        )
        assert await previews.stop(facts.id) is True
        await asyncio.sleep(0.2)
        assert stranger.returncode is None
    finally:
        stranger.kill()
        await stranger.wait()


async def test_the_sweep_stops_the_preview_of_a_ticket_that_is_no_longer_open(
    previews: PreviewService, facts: TicketFacts
) -> None:
    await previews.start(facts.id)
    assert await previews.sweep({facts.id}, NOW) == []
    assert await previews.sweep(set(), NOW) == [facts.id]
    assert await previews.running() == []


async def test_the_sweep_stops_a_preview_idle_for_the_limit_not_a_second_before(
    previews: PreviewService, facts: TicketFacts, clock: FakeClock
) -> None:
    await previews.start(facts.id)
    clock.advance(59)
    assert await previews.sweep({facts.id}, clock.now) == []
    clock.advance(1)
    assert await previews.sweep({facts.id}, clock.now) == [facts.id]


async def test_the_sweep_keeps_a_preview_when_the_repository_sets_no_idle_limit(
    previews: PreviewService, fakes: Fakes, facts: TicketFacts, clock: FakeClock
) -> None:
    await previews.start(facts.id)
    fakes.config.value = Settings(preview_command="sleep 30")
    clock.advance(10_000)
    assert await previews.sweep({facts.id}, clock.now) == []
    await previews.stop(facts.id)


async def test_a_free_port_can_be_bound_and_is_unprivileged() -> None:
    port = await free_port()
    assert 1024 <= port <= 65535
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
