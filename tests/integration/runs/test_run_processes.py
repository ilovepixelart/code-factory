"""Real children: a spawned run has its own group, stop ends it, a recycled pid is left alone."""

import asyncio
import contextlib
import os
import signal
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import override

import pytest

from code_factory.runs.adapters import processes
from code_factory.runs.adapters.processes import ProcessRegistry, Target
from code_factory.runs.adapters.ps import Ps

ENV = {"PATH": "/usr/bin:/bin"}
TERM_GRACE_S = 0.3


@pytest.fixture
async def registry() -> AsyncGenerator[ProcessRegistry]:
    held = ProcessRegistry(term_grace_s=TERM_GRACE_S)
    kill = processes.signal_group  # the real one: a test may replace it with a recorder
    yield held
    for pid in held.pids():
        kill(pid, signal.SIGKILL)
    await held.reap_all()


@pytest.fixture
def signals(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Every signal the registry would send; the real one is replaced, so nothing is ever sent."""
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(processes, "signal_group", lambda pgid, sig: sent.append((pgid, sig)))
    return sent


async def spawn(registry: ProcessRegistry, tmp_path: Path, script: str) -> Target:
    exit_file = tmp_path / "ab12cd34ef56.exit"
    spawned = await registry.spawn(
        ["/bin/sh", "-c", script, str(exit_file)], env=ENV, cwd=tmp_path, log=tmp_path / "run.log"
    )
    return Target(pid=spawned.pid, started_at=spawned.started_at, exit_file=exit_file)


async def _end_with_its_child(child: asyncio.subprocess.Process) -> None:
    """End a shell started in this test's own group and the sleep it runs, which outlives it."""
    for _ in range(40):  # the sleep may not have started yet
        orphans = await asyncio.create_subprocess_exec("/usr/bin/pkill", "-P", str(child.pid))
        if await orphans.wait() == 0:
            break
        await asyncio.sleep(0.05)
    with contextlib.suppress(ProcessLookupError):  # the shell ends by itself once its sleep does
        child.kill()
    await child.wait()


async def gone(registry: ProcessRegistry, target: Target) -> bool:
    for _ in range(100):
        if not await registry.alive(target):
            return True
        await asyncio.sleep(0.05)
    return False


async def test_a_spawned_run_leads_its_own_group_and_records_when_it_started(
    registry: ProcessRegistry, tmp_path: Path
) -> None:
    target = await spawn(registry, tmp_path, "sleep 30; :")
    assert os.getpgid(target.pid) == target.pid
    assert os.getpgid(target.pid) != os.getpgid(0)
    assert target.started_at is not None
    assert abs((datetime.now(UTC) - target.started_at).total_seconds()) < 5
    assert await registry.alive(target)


async def test_the_log_is_created_private_and_receives_the_output(
    registry: ProcessRegistry, tmp_path: Path
) -> None:
    target = await spawn(registry, tmp_path, "echo hello; echo oops >&2")
    assert await gone(registry, target)
    log = tmp_path / "run.log"
    assert sorted(log.read_text().split()) == ["hello", "oops"]
    assert log.stat().st_mode & 0o777 == 0o600


async def test_a_log_that_already_exists_is_never_followed_or_reused(
    registry: ProcessRegistry, tmp_path: Path
) -> None:
    (tmp_path / "real.log").write_text("keep")
    (tmp_path / "run.log").symlink_to(tmp_path / "real.log")
    with pytest.raises(FileExistsError):
        await spawn(registry, tmp_path, "echo hi")
    assert (tmp_path / "real.log").read_text() == "keep"


async def test_stop_ends_the_whole_group_and_reaps_the_child(
    registry: ProcessRegistry, tmp_path: Path
) -> None:
    target = await spawn(registry, tmp_path, "sleep 30 & sleep 30; :")
    await registry.stop(target)
    assert not await registry.alive(target)
    assert registry.returncode(target.pid) == -signal.SIGTERM


async def test_a_child_that_ignores_term_is_killed_after_the_grace(
    registry: ProcessRegistry, tmp_path: Path
) -> None:
    target = await spawn(registry, tmp_path, "trap '' TERM; while :; do sleep 0.1; done")
    await asyncio.sleep(0.2)
    await registry.stop(target)
    assert registry.returncode(target.pid) == -signal.SIGKILL


@pytest.mark.parametrize("pid", [1, 0, -1, 2**31])
async def test_no_group_at_or_below_pid_one_is_signalled_even_when_held(
    registry: ProcessRegistry, signals: list[tuple[int, int]], pid: int, tmp_path: Path
) -> None:
    target = Target(pid=pid, started_at=None, exit_file=tmp_path / "x.exit")
    assert await registry.send_signal(target, signal.SIGTERM) is False
    assert signals == []


async def test_a_pid_nobody_started_and_nobody_verified_is_not_signalled(
    signals: list[tuple[int, int]], tmp_path: Path
) -> None:
    child = await asyncio.create_subprocess_exec("/bin/sleep", "30", start_new_session=True)
    try:
        fresh = ProcessRegistry()
        stranger = Target(pid=child.pid, started_at=None, exit_file=tmp_path / "ab.exit")
        assert await fresh.send_signal(stranger, signal.SIGTERM) is False
        assert signals == []
    finally:
        await _end_with_its_child(child)


async def test_a_recycled_pid_is_not_the_recorded_process(
    registry: ProcessRegistry, signals: list[tuple[int, int]], tmp_path: Path
) -> None:
    target = await spawn(registry, tmp_path, "sleep 30; :")
    fresh = ProcessRegistry()
    stale = Target(
        pid=target.pid,
        started_at=target.started_at.replace(year=2020) if target.started_at else None,
        exit_file=target.exit_file,
    )
    assert await fresh.send_signal(stale, signal.SIGTERM) is False
    assert signals == []


async def test_a_run_a_restarted_board_finds_by_its_start_and_exit_file_can_be_stopped(
    registry: ProcessRegistry, tmp_path: Path
) -> None:
    target = await spawn(registry, tmp_path, "sleep 30; :")
    restarted = ProcessRegistry(term_grace_s=TERM_GRACE_S)
    assert await restarted.alive(target)
    await restarted.stop(target)
    assert await gone(restarted, target)


async def test_detaching_leaves_the_child_running(tmp_path: Path) -> None:
    held = ProcessRegistry()
    target = await spawn(held, tmp_path, "sleep 30; :")
    held.detach_all()
    try:
        assert await ProcessRegistry().alive(target)
    finally:
        await ProcessRegistry(term_grace_s=TERM_GRACE_S).stop(target)


@pytest.mark.parametrize(("holds", "collections"), [(False, 0), (True, 1)])
async def test_letting_go_collects_only_when_a_process_was_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, holds: bool, collections: int
) -> None:
    """A full collection finalises the transports let go of; with none held it is pure cost."""
    registry = ProcessRegistry()
    target = await spawn(registry, tmp_path, "sleep 30; :") if holds else None
    counted: list[int] = []
    monkeypatch.setattr(processes.gc, "collect", lambda: counted.append(1) or 0)
    try:
        registry.detach_all()
        assert len(counted) == collections
    finally:
        if target is not None:
            await ProcessRegistry(term_grace_s=TERM_GRACE_S).stop(target)


class _AnyProcess:
    """A `ps` that says every pid started at the recorded time with the exit file in its command."""

    def __init__(self, started: float, exit_file: Path) -> None:
        self._started = started
        self._exit_file = exit_file

    async def start_time(self, pid: int) -> float | None:  # noqa: ARG002
        return self._started

    async def command(self, pid: int) -> str | None:  # noqa: ARG002
        return f"/bin/sh wrapper {self._exit_file.name}"


@pytest.mark.parametrize("pid", [1, 0, -1, 2**31])
async def test_the_pid_bounds_hold_even_when_ps_vouches_for_the_process(
    signals: list[tuple[int, int]], pid: int, tmp_path: Path
) -> None:
    exit_file = tmp_path / "ab12cd34ef56.exit"
    fresh = ProcessRegistry(ps=_AnyProcess(1000.0, exit_file))  # ty: ignore[invalid-argument-type]
    target = Target(pid=pid, started_at=datetime.fromtimestamp(1000.0, UTC), exit_file=exit_file)
    assert await fresh.send_signal(target, signal.SIGKILL) is False
    assert signals == []


async def test_a_matching_process_that_does_not_lead_its_group_is_not_signalled(
    signals: list[tuple[int, int]], tmp_path: Path
) -> None:
    exit_file = tmp_path / "ab12cd34ef56.exit"
    child = await asyncio.create_subprocess_exec(
        "/bin/sh", "-c", "sleep 30; :", str(exit_file)
    )  # same group as this test process
    try:
        started = await Ps().start_time(child.pid)
        assert started is not None
        target = Target(child.pid, datetime.fromtimestamp(started, UTC), exit_file)
        assert await ProcessRegistry().alive(target) is False
        assert await ProcessRegistry().send_signal(target, signal.SIGKILL) is False
        assert signals == []
    finally:
        await _end_with_its_child(child)


async def test_a_process_that_could_not_be_looked_up_when_cancelled_is_not_left_running(
    tmp_path: Path,
) -> None:
    class CancelledPs(Ps):
        @override
        async def start_time(self, pid: int) -> float | None:
            raise asyncio.CancelledError

    held = ProcessRegistry(CancelledPs(), term_grace_s=TERM_GRACE_S)
    with pytest.raises(asyncio.CancelledError):
        await spawn(held, tmp_path, "sleep 30; :")
    (pid,) = held.pids()
    for _ in range(100):
        if held.returncode(pid) is not None:
            break
        await asyncio.sleep(0.05)
    assert held.returncode(pid) == -signal.SIGKILL


async def test_leftovers_are_killed_once_and_the_pid_is_never_signalled_again(
    registry: ProcessRegistry,
    tmp_path: Path,
    signals: list[tuple[int, int]],
) -> None:
    target = await spawn(registry, tmp_path, "sleep 30; :")
    registry.end_leftovers(target)
    assert signals == [(target.pid, signal.SIGKILL)]
    registry.end_leftovers(target)
    assert await registry.send_signal(target, signal.SIGKILL) is False
    assert signals == [(target.pid, signal.SIGKILL)]
    os.killpg(target.pid, signal.SIGKILL)


async def test_a_held_process_that_was_reaped_is_not_signalled_again(
    registry: ProcessRegistry, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = await spawn(registry, tmp_path, "sleep 30; :")
    await registry.stop(target)
    assert registry.returncode(target.pid) is not None
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(processes, "signal_group", lambda pgid, sig: sent.append((pgid, sig)))
    await registry.stop(target)
    assert await registry.send_signal(target, signal.SIGKILL) is False
    assert await registry.kill(target) is False
    assert sent == []


async def test_the_leftovers_of_a_leader_that_exited_are_still_killed(
    registry: ProcessRegistry, tmp_path: Path, signals: list[tuple[int, int]]
) -> None:
    target = await spawn(registry, tmp_path, "exit 0")
    assert await gone(registry, target)
    registry.end_leftovers(target)
    assert signals == [(target.pid, signal.SIGKILL)]
