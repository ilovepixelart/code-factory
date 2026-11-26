"""`code-factory open`: signs the default browser in to a server that already runs."""

import argparse
import http.server
import re
import socket
import threading
from collections.abc import Iterator
from datetime import timedelta
from typing import override

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from code_factory.app import main
from code_factory.auth.cli import open_command
from code_factory.auth.service import AuthService
from code_factory.platform.config import load_settings
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError
from code_factory.platform.services import Services


class _Health(http.server.BaseHTTPRequestHandler):
    status = 200
    body = b'{"status":"ok"}'
    redirect_to: str | None = None

    def do_GET(self) -> None:  # the name http.server calls
        if self.path == "/elsewhere":  # a healthy answer, from an endpoint nobody asked
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        if self.path != "/api/health":
            self.send_response(404)
            self.end_headers()
            return
        if self.redirect_to is not None:
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.end_headers()
            return
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(self.body)

    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output clean."""


@pytest.fixture
def health_port() -> Iterator[int]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_address[1])
    server.shutdown()
    server.server_close()


def _unused_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(autouse=True)
def _url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_FACTORY_DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/x_test")


def test_it_refuses_with_one_sentence_when_nothing_answers_on_the_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _unused_port()
    monkeypatch.setenv("CODE_FACTORY_PORT", str(port))
    command = open_command(lambda _link: True)
    assert command.check is not None
    with pytest.raises(BadRequestError) as raised:
        command.check(load_settings())
    assert str(raised.value) == (
        f"nothing answers at http://127.0.0.1:{port}/api/health; "
        "start the board with `code-factory serve` first"
    )


def test_it_refuses_when_the_port_answers_but_is_not_healthy(
    monkeypatch: pytest.MonkeyPatch, health_port: int
) -> None:
    monkeypatch.setattr(_Health, "status", 500)
    monkeypatch.setenv("CODE_FACTORY_PORT", str(health_port))
    command = open_command(lambda _link: True)
    assert command.check is not None
    with pytest.raises(BadRequestError, match="nothing answers at"):
        command.check(load_settings())


def test_it_refuses_a_service_that_answers_ok_but_is_not_the_board(
    monkeypatch: pytest.MonkeyPatch, health_port: int
) -> None:
    monkeypatch.setattr(_Health, "body", b"<html>welcome</html>")
    monkeypatch.setenv("CODE_FACTORY_PORT", str(health_port))
    command = open_command(lambda _link: True)
    assert command.check is not None
    with pytest.raises(BadRequestError, match="nothing answers at"):
        command.check(load_settings())


def test_it_does_not_follow_a_redirect_to_another_endpoint(
    monkeypatch: pytest.MonkeyPatch, health_port: int
) -> None:
    monkeypatch.setattr(_Health, "redirect_to", f"http://127.0.0.1:{health_port}/elsewhere")
    monkeypatch.setenv("CODE_FACTORY_PORT", str(health_port))
    command = open_command(lambda _link: True)
    assert command.check is not None
    with pytest.raises(BadRequestError, match="nothing answers at"):
        command.check(load_settings())


def test_it_refuses_port_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_FACTORY_PORT", "0")
    command = open_command(lambda _link: True)
    assert command.check is not None
    with pytest.raises(BadRequestError, match="port the server printed"):
        command.check(load_settings())


def test_it_accepts_a_server_that_answers_health(
    monkeypatch: pytest.MonkeyPatch, health_port: int
) -> None:
    monkeypatch.setattr(_Health, "status", 200)
    monkeypatch.setenv("CODE_FACTORY_PORT", str(health_port))
    command = open_command(lambda _link: True)
    assert command.check is not None
    command.check(load_settings())


async def test_it_opens_a_link_that_signs_in_once(
    connection: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODE_FACTORY_PORT", "4123")
    auth = AuthService(
        UnitOfWork(
            async_sessionmaker(
                bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
        )
    )
    services = Services()
    services.add(AuthService, auth)
    opened: list[str] = []
    threads: list[str] = []

    def opener(link: str) -> bool:
        opened.append(link)
        threads.append(threading.current_thread().name)
        return True

    command = open_command(opener)
    assert command.run_async is not None

    code = await command.run_async(argparse.Namespace(), services)

    assert code == 0
    assert threads != [threading.main_thread().name]
    found = re.fullmatch(r"http://127\.0\.0\.1:4123/owner/(cfn_[A-Za-z0-9_-]{43})", opened[0])
    assert found is not None
    assert await auth.redeem_sign_in_nonce(found.group(1), lifetime=timedelta(days=1))


async def test_it_fails_with_one_sentence_when_no_browser_could_be_launched(
    connection: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODE_FACTORY_PORT", "4123")
    services = Services()
    services.add(
        AuthService,
        AuthService(
            UnitOfWork(
                async_sessionmaker(
                    bind=connection,
                    join_transaction_mode="create_savepoint",
                    expire_on_commit=False,
                )
            )
        ),
    )
    command = open_command(lambda _link: False)
    assert command.run_async is not None
    with pytest.raises(BadRequestError) as raised:
        await command.run_async(argparse.Namespace(), services)
    assert str(raised.value) == (
        "no browser could be launched; run `code-factory sign-in` for a link to open yourself"
    )


def test_the_help_says_what_it_does(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in (["--help"], ["open", "--help"]):
        with pytest.raises(SystemExit):
            main(argv)
        assert "sign the default browser in to the running server" in " ".join(
            capsys.readouterr().out.split()
        )
