"""`serve` opens the default browser signed in, only on a terminal and never when told not to."""

import os
import pty
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from starlette.applications import Starlette

from code_factory.platform.cli import AnnouncingServer, wants_browser

LINK = "http://127.0.0.1:4999/owner/cfn_abc"
COMMAND = str(Path(sys.executable).parent / "code-factory")


@pytest.mark.parametrize(
    ("no_open", "setting", "terminal", "expected"),
    [
        (False, True, True, True),
        (True, True, True, False),
        (False, False, True, False),
        (False, True, False, False),
        (True, False, False, False),
    ],
)
def test_the_browser_is_wanted_only_on_a_terminal_and_when_not_switched_off(
    *, no_open: bool, setting: bool, terminal: bool, expected: bool
) -> None:
    assert wants_browser(no_open=no_open, setting=setting, is_terminal=terminal) is expected


def _serve_briefly(lines: list[str], opener: object | None) -> None:
    app = Starlette()
    app.state.startup_lines = lines
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        config = uvicorn.Config(app, log_config=None)
        server = AnnouncingServer(config, "http://127.0.0.1", opener)  # ty: ignore[invalid-argument-type]
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]))
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        time.sleep(0.2)  # the opener runs in a worker thread
        server.should_exit = True
        thread.join(timeout=10)


def test_the_started_server_opens_the_sign_in_link_it_printed() -> None:
    opened: list[str] = []
    _serve_briefly([f"sign in: {LINK}"], opened.append)
    assert opened == [LINK]


def test_the_opener_runs_off_the_event_loop_thread() -> None:
    threads: list[str] = []
    _serve_briefly(
        [f"sign in: {LINK}"], lambda _link: threads.append(threading.current_thread().name)
    )
    assert threads == ["open-browser"]


def test_nothing_is_opened_without_an_opener_or_without_a_link() -> None:
    opened: list[str] = []
    _serve_briefly([f"sign in: {LINK}"], None)
    _serve_briefly(["something else"], opened.append)
    assert opened == []


def _browser_script(tmp_path: Path) -> tuple[Path, Path]:
    marker = tmp_path / "opened.txt"
    script = tmp_path / "browser.sh"
    script.write_text(f'#!/bin/sh\necho "$1" > "{marker}"\n')
    script.chmod(0o755)
    return script, marker


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _run_serve(
    serve_env: dict[str, str], tmp_path: Path, *extra: str, terminal: bool, **env: str
) -> list[str]:
    """Start `serve` with a fake browser in `BROWSER`, wait for its sign-in line, stop it."""
    script, _ = _browser_script(tmp_path)
    full = {
        **serve_env,
        "BROWSER": f"{script} %s",
        "CODE_FACTORY_PORT": str(_free_port()),
        "CODE_FACTORY_STOP_AT_EOF": "1",
        "CODE_FACTORY_OPEN": "true",  # a developer's own setting must not decide these tests
        **env,
    }
    master = slave = None
    if terminal:
        master, slave = pty.openpty()
    process = subprocess.Popen(  # noqa: S603  # our own console script, no shell
        [COMMAND, "serve", *extra],
        env=full,
        stdin=subprocess.PIPE,
        stdout=slave if slave is not None else subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    seen: list[str] = []
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not any("sign in:" in line for line in seen):
            assert process.poll() is None, "the server exited during startup"
            if master is not None:
                seen.append(os.read(master, 4096).decode())
            else:
                assert process.stdout is not None
                seen.append(process.stdout.readline())
        time.sleep(1.0)  # the browser would have been started by now
    finally:
        assert process.stdin is not None
        process.stdin.close()
        process.wait(timeout=20)
        if process.stdout is not None:
            process.stdout.close()
        for fd in (master, slave):
            if fd is not None:
                os.close(fd)
    return seen


def test_serve_on_a_terminal_opens_the_default_browser_with_the_link(
    serve_env: dict[str, str], tmp_path: Path
) -> None:
    _run_serve(serve_env, tmp_path, terminal=True)
    opened = (tmp_path / "opened.txt").read_text().strip()
    assert opened.startswith("http://127.0.0.1:")
    assert "/owner/cfn_" in opened


def test_serve_with_stdout_not_a_terminal_opens_nothing(
    serve_env: dict[str, str], tmp_path: Path
) -> None:
    _run_serve(serve_env, tmp_path, terminal=False)
    assert not (tmp_path / "opened.txt").exists()


def test_serve_no_open_opens_nothing_even_on_a_terminal(
    serve_env: dict[str, str], tmp_path: Path
) -> None:
    _run_serve(serve_env, tmp_path, "--no-open", terminal=True)
    assert not (tmp_path / "opened.txt").exists()


def test_the_open_setting_false_opens_nothing_even_on_a_terminal(
    serve_env: dict[str, str], tmp_path: Path
) -> None:
    _run_serve(serve_env, tmp_path, terminal=True, CODE_FACTORY_OPEN="false")
    assert not (tmp_path / "opened.txt").exists()


def test_the_browser_test_launcher_never_opens_a_browser() -> None:
    launcher = (Path(__file__).resolve().parents[3] / "web/e2e/fixtures.ts").read_text()
    assert "CODE_FACTORY_OPEN: 'false'" in launcher


def test_a_slow_opener_does_not_hold_the_server_back() -> None:
    start = time.monotonic()
    _serve_briefly([f"sign in: {LINK}"], lambda _link: time.sleep(1.5))
    assert time.monotonic() - start < 1.4
