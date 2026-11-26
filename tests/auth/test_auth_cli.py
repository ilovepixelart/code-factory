"""`code-factory token create|list|revoke`: the owner's way to hold and end MCP credentials."""

import argparse
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from code_factory.auth.cli import token_command
from code_factory.auth.service import AuthService
from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.services import Services
from mcp_support import isolated_unit_of_work


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="token")
    token_command.configure(parser)
    return parser.parse_args(argv)


async def _run(connection: AsyncConnection, *argv: str) -> tuple[int, AuthService]:
    auth = AuthService(isolated_unit_of_work(connection))
    services = Services()
    services.add(AuthService, auth)
    run_async = token_command.run_async
    assert run_async is not None
    return await run_async(_parse(*argv), services), auth


async def test_create_prints_the_token_alone_on_stdout_and_it_verifies_as_that_owner(
    connection: AsyncConnection, capsys: pytest.CaptureFixture[str]
) -> None:
    code, auth = await _run(connection, "create", "--label", "alex laptop", "--days", "30")
    captured = capsys.readouterr()
    token = captured.out.strip()
    assert (code, token.startswith("cfo_"), "\n" in token) == (0, True, False)
    assert "shown once" in captured.err
    actor = await auth.verify_token(token)
    assert actor is not None
    assert actor.subject == "owner:alex laptop"
    assert (actor.expires_at - (await auth.list_tokens())[0].created_at) == timedelta(days=30)


async def test_create_needs_a_label(connection: AsyncConnection) -> None:
    with pytest.raises(BadRequestError, match="create needs --label"):
        await _run(connection, "create")


async def test_list_shows_id_kind_label_and_expiry_but_never_a_token(
    connection: AsyncConnection, capsys: pytest.CaptureFixture[str]
) -> None:
    _, auth = await _run(connection, "create", "--label", "one")
    token = capsys.readouterr().out.strip()
    code, _ = await _run(connection, "list")
    out = capsys.readouterr().out
    info = (await auth.list_tokens())[0]
    assert code == 0
    assert out.splitlines()[0].split() == ["ID", "KIND", "LABEL", "EXPIRES", "LAST_USED"]
    row = out.splitlines()[1].split()
    assert row[:3] == [str(info.id), "owner", "one"]
    assert token not in out


async def test_revoke_ends_the_token_and_names_it(
    connection: AsyncConnection, capsys: pytest.CaptureFixture[str]
) -> None:
    _, auth = await _run(connection, "create", "--label", "gone")
    token = capsys.readouterr().out.strip()
    info = (await auth.list_tokens())[0]
    code, _ = await _run(connection, "revoke", str(info.id))
    assert (code, capsys.readouterr().out) == (0, f"revoked token {info.id} (gone)\n")
    assert await auth.verify_token(token) is None


async def test_revoking_an_unknown_token_says_which(connection: AsyncConnection) -> None:
    with pytest.raises(NotFoundError, match="no live token with id 99999"):
        await _run(connection, "revoke", "99999")


async def test_revoke_needs_an_id(connection: AsyncConnection) -> None:
    with pytest.raises(BadRequestError, match="revoke needs the token's id"):
        await _run(connection, "revoke")


async def test_the_command_manages_owner_tokens_only(
    connection: AsyncConnection, capsys: pytest.CaptureFixture[str]
) -> None:
    code, auth = await _run(connection, "create", "--label", "mine")
    capsys.readouterr()
    run = await auth.issue_run_token(
        run_id="r", ticket_id="CF-1", stage="spec", repository="/r", lifetime=timedelta(hours=1)
    )
    nonce = await auth.issue_sign_in_nonce("mine")
    session = await auth.redeem_sign_in_nonce(
        nonce.token.get_secret_value(), lifetime=timedelta(hours=1)
    )
    assert session is not None
    await _run(connection, "list")
    rows = capsys.readouterr().out.splitlines()[1:]
    assert [row.split()[1] for row in rows] == ["owner"]
    for foreign in (run.id, session.id):
        with pytest.raises(NotFoundError, match=f"no live token with id {foreign}"):
            await _run(connection, "revoke", str(foreign))
    assert await auth.verify_token(run.token.get_secret_value()) is not None
    assert code == 0


@pytest.mark.parametrize("days", ["0", "-1", "367", "1000000000"])
async def test_a_lifetime_outside_one_to_366_days_is_refused_with_a_sentence(
    connection: AsyncConnection, days: str
) -> None:
    with pytest.raises(BadRequestError, match="--days is a whole number from 1 to 366"):
        await _run(connection, "create", "--label", "x", "--days", days)
