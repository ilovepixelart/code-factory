"""`code-factory sign-in`: a new link for a running board."""

import pytest

from code_factory.app import main
from code_factory.auth.cli import command
from code_factory.platform.config import load_settings
from code_factory.platform.errors import BadRequestError


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
