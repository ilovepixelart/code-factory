"""The heavy-step lock: a real symlink and real child processes as its holders."""

import asyncio
import os
import signal
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from code_factory.checks.adapters import HeavyLockFile
from code_factory.checks.rules import board_text


@asynccontextmanager
async def child(name: str = "sleeper") -> AsyncGenerator[asyncio.subprocess.Process]:
    """A process that lives until the block ends; `name` shows in its command line."""
    process = await asyncio.create_subprocess_exec(
        "/bin/sh", "-c", "sleep 30; exit 0", name, start_new_session=True
    )
    try:
        yield process
    finally:
        assert process.pid > 1  # a group id this test started
        os.killpg(process.pid, signal.SIGKILL)
        await process.wait()


class Said:
    def __init__(self) -> None:
        self.lines: list[str] = []

    async def __call__(self, line: str) -> None:
        self.lines.append(line)


async def test_a_free_lock_is_taken_and_released_only_while_it_is_still_ours(
    tmp_path: Path,
) -> None:
    link = tmp_path / "locks" / "gate-heavy.lock"
    held = await HeavyLockFile(link).take(board_text(os.getpid(), "/t"), 5, Said())
    assert held.held
    assert link.readlink() == Path(board_text(os.getpid(), "/t"))
    await held.release()
    assert not link.is_symlink()

    again = await HeavyLockFile(link).take("1234 container in /t on the board", 5, Said())
    link.unlink()
    link.symlink_to("9999 rust-test in /other on b")  # another process now holds it
    await again.release()
    assert link.readlink() == Path("9999 rust-test in /other on b")


async def test_a_gone_holder_is_released_and_its_lock_taken(tmp_path: Path) -> None:
    link = tmp_path / "gate-heavy.lock"
    dead = await asyncio.create_subprocess_exec("/bin/sh", "-c", "exit 0")
    await dead.wait()
    link.symlink_to(f"{dead.pid} rust-test in /t on b")
    said = Said()
    held = await HeavyLockFile(link).take("me", 5, said)
    assert held.held
    assert said.lines == []  # a gone holder is released without a wait to tell of


async def test_a_live_process_that_is_no_gate_loses_its_lock(tmp_path: Path) -> None:
    link = tmp_path / "gate-heavy.lock"
    async with child("vim-notes") as holder:
        link.symlink_to(f"{holder.pid} rust-test in /t on b")
        held = await HeavyLockFile(link).take("me", 5, Said())
    assert held.held
    assert link.readlink() == Path("me")


async def test_a_live_gate_is_waited_for_until_the_bound_and_then_the_board_goes_on(
    tmp_path: Path,
) -> None:
    link = tmp_path / "gate-heavy.lock"
    async with child("gate.sh") as holder:
        text = f"{holder.pid} rust-test in /t on b"
        link.symlink_to(text)
        said = Said()
        held = await HeavyLockFile(link).take("me", 1, said)
    assert not held.held
    assert said.lines == [
        f"waits for the heavy-step lock, held by pid {holder.pid}: rust-test in /t on b",
        (
            f"runs without the heavy-step lock: held over 1s, now by pid {holder.pid}: "
            "rust-test in /t on b"
        ),
    ]
    assert link.readlink() == Path(text)  # a hold that is empty removes nothing
    await held.release()
    assert link.is_symlink()


async def test_the_lock_is_taken_when_its_holder_lets_go_while_the_board_waits(
    tmp_path: Path,
) -> None:
    link = tmp_path / "gate-heavy.lock"
    async with child("gate.sh") as holder:
        link.symlink_to(f"{holder.pid} rust-test in /t on b")

        async def let_go() -> None:
            await asyncio.sleep(0.4)
            link.unlink()

        letting = asyncio.create_task(let_go())
        held = await HeavyLockFile(link).take("me", 30, Said())
        await letting
    assert held.held


async def test_a_pid_of_zero_or_one_is_never_probed(tmp_path: Path) -> None:
    probed: list[int] = []

    def kill(pid: int, _sig: int) -> None:
        probed.append(pid)
        raise ProcessLookupError

    for pid in (0, 1):
        link = tmp_path / f"lock{pid}"
        link.symlink_to(f"{pid} rust-test in /t on b")
        held = await HeavyLockFile(link, kill=kill).take("me", 5, Said())
        assert held.held
    assert probed == []


async def test_a_folder_that_cannot_hold_a_link_goes_on_without_the_lock(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    held = await HeavyLockFile(blocker / "gate-heavy.lock").take("me", 5, Said())
    assert not held.held


async def test_a_lock_path_that_is_not_a_symlink_is_not_waited_for(tmp_path: Path) -> None:
    link = tmp_path / "gate-heavy.lock"
    link.write_text("not a lock")
    held = await asyncio.wait_for(
        HeavyLockFile(link).take(board_text(os.getpid(), "/t"), 1800, Said()), timeout=5
    )
    assert not held.held
    assert link.read_text() == "not a lock"
