"""`code-factory sign-in`: a new link for a running board."""

import argparse
import re
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from code_factory.app import main
from code_factory.auth.cli import command
from code_factory.auth.service import AuthService
from code_factory.platform.config import load_settings
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError
from code_factory.platform.services import Services


async def test_it_prints_a_link_that_signs_in_once(
    connection: AsyncConnection,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_FACTORY_PORT", "4123")
    monkeypatch.setenv("CODE_FACTORY_HOST", "127.0.0.1")
    auth = AuthService(
        UnitOfWork(
            async_sessionmaker(
                bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
        )
    )
    services = Services()
    services.add(AuthService, auth)
    assert command.run_async is not None

    code = await command.run_async(argparse.Namespace(), services)

    out = capsys.readouterr().out.splitlines()[0]
    found = re.fullmatch(r"http://127\.0\.0\.1:4123/owner/(cfn_[A-Za-z0-9_-]{43})", out)
    assert (code, found is not None) == (0, True)
    assert found is not None
    assert await auth.redeem_sign_in_nonce(found.group(1), lifetime=timedelta(days=1))


async def test_it_refuses_port_zero_because_the_real_port_is_known_only_to_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_FACTORY_PORT", "0")
    monkeypatch.setenv("CODE_FACTORY_DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/x_test")
    assert command.check is not None
    with pytest.raises(BadRequestError, match="port the server printed"):
        command.check(load_settings())


SIGN_IN_SUMMARY = (
    "print a one-time link that signs you in in the browser, valid for 60 seconds "
    "(reads the same env files as serve)"
)


def _help(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    with pytest.raises(SystemExit) as stopped:
        main([*argv, "--help"])
    assert stopped.value.code == 0
    return " ".join(capsys.readouterr().out.split())


def test_the_top_level_help_describes_sign_in(capsys: pytest.CaptureFixture[str]) -> None:
    assert SIGN_IN_SUMMARY in _help(capsys)


def test_the_sign_in_help_describes_it_too(capsys: pytest.CaptureFixture[str]) -> None:
    assert SIGN_IN_SUMMARY in _help(capsys, "sign-in")


async def test_the_output_says_to_open_the_link_within_60_seconds(
    connection: AsyncConnection,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
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
    assert command.run_async is not None

    await command.run_async(argparse.Namespace(), services)

    link, note = capsys.readouterr().out.splitlines()
    assert link.startswith("http://127.0.0.1:4123/owner/cfn_")
    assert note == "Open it in the browser within 60 seconds."
