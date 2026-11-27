"""`code-factory token create|list|revoke` and `sign-in`: the owner's credentials."""

import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from datetime import timedelta
from typing import override

from code_factory.auth.models import TokenKind
from code_factory.auth.rules import LONGEST_LIFETIME
from code_factory.auth.service import AuthService
from code_factory.platform.config import Settings, load_settings
from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.module import Command
from code_factory.platform.services import Services

OWNER_LABEL = "owner"
DEFAULT_DAYS = 30
OWNER_TOKENS = {TokenKind.OWNER}  # sessions and nonces are the browser's, runs' are the board's
LONGEST_DAYS = LONGEST_LIFETIME[TokenKind.OWNER].days


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["create", "list", "revoke"])
    parser.add_argument("id", nargs="?", type=int, help="the token to revoke (see `list`)")
    parser.add_argument("--label", help="create: what the token is for, for example a machine")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="create: lifetime in days")


async def _create(args: argparse.Namespace, auth: AuthService) -> None:
    if not args.label:
        raise BadRequestError("create needs --label: say what the token is for")
    if not 1 <= args.days <= LONGEST_DAYS:
        msg = f"--days is a whole number from 1 to {LONGEST_DAYS}"
        raise BadRequestError(msg)
    issued = await auth.issue_owner_token(args.label, lifetime=timedelta(days=args.days))
    sys.stdout.write(issued.token.get_secret_value() + "\n")
    sys.stderr.write(
        f"token {issued.id} ({args.label}) expires {issued.expires_at:%Y-%m-%d}; "
        "the value is shown once and is not stored; put it in CODE_FACTORY_MCP_TOKEN\n"
    )


async def _list(auth: AuthService) -> None:
    sys.stdout.write("ID  KIND  LABEL  EXPIRES  LAST_USED\n")
    for info in await auth.list_tokens(kinds=OWNER_TOKENS):
        used = "never" if info.last_used_at is None else f"{info.last_used_at:%Y-%m-%d %H:%M}"
        sys.stdout.write(
            f"{info.id}  {info.kind.value}  {info.label or info.subject}  "
            f"{info.expires_at:%Y-%m-%d}  {used}\n"
        )


async def _revoke(args: argparse.Namespace, auth: AuthService) -> None:
    if args.id is None:
        raise BadRequestError("revoke needs the token's id; `code-factory token list` shows them")
    live = {info.id: info for info in await auth.list_tokens(kinds=OWNER_TOKENS)}
    if args.id not in live or not await auth.revoke(args.id, kinds=OWNER_TOKENS):
        msg = f"no live token with id {args.id}; `code-factory token list` shows them"
        raise NotFoundError(msg)
    sys.stdout.write(f"revoked token {args.id} ({live[args.id].label or live[args.id].subject})\n")


async def _run(args: argparse.Namespace, services: Services) -> int:
    auth = services.get(AuthService)
    if args.action == "create":
        await _create(args, auth)
    elif args.action == "list":
        await _list(auth)
    else:
        await _revoke(args, auth)
    return 0


token_command = Command(
    "token",
    "create, list or revoke the owner's MCP tokens",
    configure=_configure,
    run_async=_run,
)


def _needs_a_port(settings: Settings) -> None:
    if settings.port == 0:
        msg = (
            "the link needs the port of the running server: set CODE_FACTORY_PORT to the port "
            "the server printed after `serving on`"
        )
        raise BadRequestError(msg)


async def _sign_in(_args: argparse.Namespace, services: Services) -> int:
    settings = load_settings()
    issued = await services.get(AuthService).issue_sign_in_nonce(OWNER_LABEL)
    link = f"{settings.base_url}/owner/{issued.token.get_secret_value()}"
    sys.stdout.write(f"{link}\nOpen it in the browser within 60 seconds.\n")
    return 0


command = Command(
    "sign-in",
    "print a one-time link that signs you in in the browser, valid for 60 seconds "
    "(reads the same env files as serve)",
    run_async=_sign_in,
    check=_needs_a_port,
)


HEALTH_TIMEOUT_S = 2.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an answer from some other endpoint, not the board's."""

    @override
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _answers(health: str) -> bool:
    """Whether the board itself answers: a direct 200 whose body is its `{"status": "ok"}`."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(health, timeout=HEALTH_TIMEOUT_S) as response:
            return bool(json.loads(response.read(1024)) == {"status": "ok"})
    except urllib.error.HTTPError as error:
        error.close()
        return False
    except OSError, ValueError:  # URLError is an OSError; bad JSON is a ValueError
        return False


def _needs_a_running_server(settings: Settings) -> None:
    _needs_a_port(settings)
    health = f"{settings.base_url}/api/health"
    if not _answers(health):
        msg = f"nothing answers at {health}; start the board with `code-factory serve` first"
        raise BadRequestError(msg)


def open_command(opener: Callable[[str], bool] = webbrowser.open) -> Command:
    """`open`: sign the default browser in to the server that already runs on the port."""

    async def run(_args: argparse.Namespace, services: Services) -> int:
        settings = load_settings()
        issued = await services.get(AuthService).issue_sign_in_nonce(OWNER_LABEL)
        link = f"{settings.base_url}/owner/{issued.token.get_secret_value()}"
        # webbrowser.open can wait on the launcher, so it runs off the event loop.
        if not await asyncio.to_thread(opener, link):
            msg = (
                "no browser could be launched; "
                "run `code-factory sign-in` for a link to open yourself"
            )
            raise BadRequestError(msg)
        return 0

    return Command(
        "open",
        "sign the default browser in to the running server (a one-time link, valid for 60 "
        "seconds; reads the same env files as serve)",
        run_async=run,
        check=_needs_a_running_server,
    )


open_server = open_command()
