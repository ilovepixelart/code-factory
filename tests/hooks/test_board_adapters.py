"""The board-process adapters: the browser opener and the probe of a running board."""

import http.server
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import override

import pytest

from code_factory.hooks.adapters.opener import BrowserOpener
from code_factory.hooks.adapters.probe import BoardProbe
from code_factory.hooks.models import OpenerUnavailableError

URL = "http://127.0.0.1:4000/owner/abc?to=%2Finbox"


def _program(folder: Path, name: str, body: str) -> None:
    path = folder / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


@pytest.fixture
def opener_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty folder as the whole `PATH`, with the platform's opener name fixed."""
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr("sys.platform", "darwin")
    return tmp_path


async def test_the_opener_hands_the_url_to_the_platform_program(opener_on_path: Path) -> None:
    log = opener_on_path / "args"
    _program(opener_on_path, "open", f'printf "%s" "$1" > {log}')

    await BrowserOpener().open_url(URL)

    assert log.read_text() == URL


async def test_linux_uses_xdg_open(opener_on_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    log = opener_on_path / "args"
    _program(opener_on_path, "xdg-open", f'printf "%s" "$1" > {log}')

    await BrowserOpener().open_url(URL)

    assert log.read_text() == URL


async def test_no_opener_program_is_unavailable(opener_on_path: Path) -> None:
    with pytest.raises(OpenerUnavailableError, match="open is not installed"):
        await BrowserOpener().open_url(URL)
    assert not list(opener_on_path.iterdir())  # noqa: ASYNC240  # the test's own temp folder


async def test_an_opener_that_fails_is_unavailable(opener_on_path: Path) -> None:
    _program(opener_on_path, "open", "exit 2")

    with pytest.raises(OpenerUnavailableError, match="open exited with 2"):
        await BrowserOpener().open_url(URL)


async def test_an_unknown_platform_has_no_opener(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "win32")

    with pytest.raises(OpenerUnavailableError, match="no browser opener for win32"):
        await BrowserOpener().open_url(URL)


async def test_an_opener_that_hangs_is_stopped(opener_on_path: Path) -> None:
    _program(opener_on_path, "open", "exec /bin/sleep 30")

    opener = BrowserOpener(timeout_s=0.2)
    with pytest.raises(OpenerUnavailableError, match=r"did not return within 0\.2 seconds"):
        await opener.open_url(URL)


class _Board(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # the http.server name
        if self.path == "/health/ready":
            self.send_response(200)
            self.end_headers()
        elif self.path == "/moved/health/ready":
            self.send_response(302)
            self.send_header("Location", "/health/ready")
            self.end_headers()
        else:
            self.send_response(503)
            self.end_headers()

    @override
    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _serving() -> Generator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Board)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def test_the_probe_sees_a_ready_board() -> None:
    with _serving() as base:
        assert await BoardProbe().up(base) is True


async def test_the_probe_does_not_follow_a_redirect() -> None:
    with _serving() as base:
        assert await BoardProbe().up(f"{base}/moved") is False


async def test_the_probe_says_down_for_a_board_that_is_not_ready() -> None:
    with _serving() as base:
        assert await BoardProbe().up(f"{base}/other") is False


async def test_the_probe_says_down_when_nothing_listens() -> None:
    with _serving() as base:
        pass
    assert await BoardProbe().up(base) is False
