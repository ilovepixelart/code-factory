"""The `code-factory` command: root parser, platform commands and the hook modules use.

A module adds subcommands through `Module.commands` (see `code_factory.platform.module.Command`);
`code_factory.app.main` passes every module's commands in, so this file imports no module.
"""

import argparse
import asyncio
import errno
import socket
import sys
import threading
import webbrowser
from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast, override

import uvicorn
from uvicorn.config import ASGIApplication

from code_factory import PACKAGE_NAME, __version__
from code_factory.platform.commands import OPENER_ARGUMENT, OpenServices
from code_factory.platform.config import Settings, load_settings
from code_factory.platform.db import EXPECTED_REVISION, check_database
from code_factory.platform.db.migrate import upgrade
from code_factory.platform.errors import CodeFactoryError, ConflictError
from code_factory.platform.logging import setup_logging
from code_factory.platform.module import Command, Module
from code_factory.platform.served import Served

EXIT_OK = 0
EXIT_FAILURE = 1


class AsgiApp(Protocol):
    """An ASGI application, however the web framework types its scope."""

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:  # noqa: ANN401
        """Handle one connection."""


class McpServer(Protocol):
    """What the `mcp` command needs of the server it runs."""

    def run(self, *, show_banner: bool) -> object:
        """Serve over stdio until the client disconnects."""


# The start-up line that carries the one-time sign-in link; `serve` opens the link it holds.
SIGN_IN_PREFIX = "sign in: "

Opener = Callable[[str], object]


def wants_browser(*, no_open: bool, setting: bool, is_terminal: bool) -> bool:
    """Whether `serve` opens the browser: a person at a terminal, not switched off."""
    return setting and is_terminal and not no_open


def _stop_when_stdin_closes(server: uvicorn.Server) -> None:
    """Ask the server to exit when standard input reaches its end (a launcher's pipe closing)."""

    def watch() -> None:
        sys.stdin.read()
        server.should_exit = True

    threading.Thread(target=watch, name="stdin-eof", daemon=True).start()


def _bind(settings: Settings) -> socket.socket:
    """The listening socket; port 0 takes a free one, which `settings.port` is then set to."""
    family, _, _, _, address = socket.getaddrinfo(
        settings.host, settings.port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )[0]
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(address)
        sock.set_inheritable(True)
    except OSError as error:
        sock.close()
        if error.errno != errno.EADDRINUSE:
            raise
        raise _in_use(settings) from None
    return sock


def _in_use(settings: Settings) -> ConflictError:
    msg = (
        f"{settings.base_url} is already in use. If Factory is already running, open that "
        "board. To start on a free port, rerun with CODE_FACTORY_PORT=0."
    )
    return ConflictError(msg)


def _bound(settings: Settings) -> Served:
    """What the plain `serve` listens on: the bound port, named by the configured link."""
    return Served(
        address=settings.host, port=settings.port, both_loopbacks=False, base_url=settings.base_url
    )


class AnnouncingServer(uvicorn.Server):
    """Prints `serving on <address>` once the server accepts connections.

    With an `opener` it then hands the printed sign-in link to it in a worker thread, so a slow
    or missing browser never holds the event loop.
    """

    def __init__(self, config: uvicorn.Config, address: str, opener: Opener | None = None) -> None:
        super().__init__(config)
        self.address = address
        self.opener = opener

    @override
    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        """Start, then say where; a failed start prints nothing."""
        await super().startup(sockets)
        if self.started:
            sys.stdout.write(f"serving on {self.address}\n")
            lines = getattr(getattr(self.config.app, "state", None), "startup_lines", [])
            for line in lines:
                sys.stdout.write(f"{line}\n")
            sys.stdout.flush()
            self._open_sign_in_link(lines)

    def _open_sign_in_link(self, lines: list[str]) -> None:
        links = [
            line.removeprefix(SIGN_IN_PREFIX) for line in lines if line.startswith(SIGN_IN_PREFIX)
        ]
        if self.opener is not None and links:
            threading.Thread(
                target=self.opener, args=(links[0],), name="open-browser", daemon=True
            ).start()


def _serve_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")


def _serve(create_app: Callable[..., AsgiApp], opener: Opener, args: argparse.Namespace) -> int:
    settings = load_settings()
    # An unusable database is reported as one sentence here, before the server starts;
    # the lifespan checks again for the case where it changed in between.
    asyncio.run(check_database(settings))
    sock = _bind(settings)
    # The host guard and the printed address need the real port, so the app is built after the bind.
    settings = settings.model_copy(update={"port": sock.getsockname()[1]})
    with setup_logging(settings.log_level), sock:
        config = uvicorn.Config(
            cast("ASGIApplication", create_app(settings, served=_bound(settings))),
            log_config=None,
            access_log=False,
            timeout_graceful_shutdown=settings.shutdown_timeout_s,
        )
        browser = wants_browser(
            no_open=args.no_open, setting=settings.open, is_terminal=sys.stdout.isatty()
        )
        server = AnnouncingServer(config, settings.base_url, opener if browser else None)
        if settings.stop_at_eof:
            _stop_when_stdin_closes(server)
        server.run(sockets=[sock])
        return EXIT_OK if server.started else EXIT_FAILURE


def _mcp(create_mcp: Callable[[Settings], McpServer]) -> int:
    settings = load_settings()
    with setup_logging(settings.log_level):
        create_mcp(settings).run(show_banner=False)
    return EXIT_OK


def _db_upgrade() -> int:
    upgrade()
    sys.stdout.write(f"database is at head ({EXPECTED_REVISION})\n")
    return EXIT_OK


def _db_check() -> int:
    state = asyncio.run(check_database(load_settings()))
    sys.stdout.write(
        f"database is at head (revision {state.revision}, data format {state.data_format})\n"
    )
    return EXIT_OK


def _runner(command: Command, open_services: OpenServices) -> Callable[[argparse.Namespace], int]:
    if command.run is not None:
        return command.run
    run_async = command.run_async
    assert run_async is not None  # noqa: S101  # Command.__post_init__ guarantees one runner

    def run(args: argparse.Namespace) -> int:
        settings = load_settings()
        if command.check is not None:
            command.check(settings)

        async def with_services() -> int:
            async with open_services(settings, database=True) as services:
                return await run_async(args, services)

        return asyncio.run(with_services())

    return run


def _add(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    command: Command,
    open_services: OpenServices,
) -> None:
    parser = commands.add_parser(command.name, help=command.help, description=command.help)
    command.configure(parser)
    # A private destination: a module option named `run` must not replace the handler.
    parser.set_defaults(
        **{"_handler": _runner(command, open_services), OPENER_ARGUMENT: open_services}
    )


def _serve_command(
    create_app: Callable[..., AsgiApp], modules: Sequence[Module], opener: Opener
) -> Command:
    """The module's `serve` when one provides it (at most one), else the plain one."""
    providers = [module for module in modules if module.serve_command is not None]
    if len(providers) > 1:
        msg = f"serve is provided by both {providers[0].name} and {providers[1].name}"
        raise ValueError(msg)
    if providers and (provide := providers[0].serve_command) is not None:
        return provide(create_app)
    return Command(
        "serve",
        "serve the API, Swagger UI and MCP over HTTP and open the browser signed in "
        "(not when stdout is not a terminal, with --no-open or CODE_FACTORY_OPEN=false)",
        run=lambda a: _serve(create_app, opener, a),
        configure=_serve_options,
    )


def _parser(
    create_app: Callable[..., AsgiApp],
    create_mcp: Callable[[Settings], McpServer],
    open_services: OpenServices,
    modules: Sequence[Module],
    opener: Opener,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PACKAGE_NAME, description="code-factory")
    parser.add_argument("--version", action="version", version=f"{PACKAGE_NAME} {__version__}")
    # For a command that describes the others (`docs`): `Command.run` gets only the Namespace.
    parser.set_defaults(root_parser=parser, modules=tuple(modules))
    commands = parser.add_subparsers(dest="command", required=True)
    own = (
        _serve_command(create_app, modules, opener),
        Command("mcp", "serve the MCP server over stdio", lambda _a: _mcp(create_mcp)),
    )
    for command in (*own, *(c for module in modules for c in module.commands)):
        _add(commands, command, open_services)
    database = commands.add_parser("db", help="database migrations").add_subparsers(
        dest="db_command", required=True
    )
    for command in (
        Command("upgrade", "migrate the database to the head revision", lambda _a: _db_upgrade()),
        Command(
            "check", "report whether the database is at the head revision", lambda _a: _db_check()
        ),
    ):
        _add(database, command, open_services)
    return parser


def main(  # noqa: PLR0913  # the composition root's injected collaborators, all keyword-only
    argv: Sequence[str] | None,
    *,
    create_app: Callable[..., AsgiApp],
    create_mcp: Callable[[Settings], McpServer],
    open_services: OpenServices,
    modules: Sequence[Module] = (),
    opener: Opener = webbrowser.open,
) -> int:
    """Run the command; an expected failure prints one sentence and returns 1."""
    args = _parser(create_app, create_mcp, open_services, modules, opener).parse_args(argv)
    try:
        return int(args._handler(args))  # noqa: SLF001  # set by _add, never a user option
    except CodeFactoryError as error:
        sys.stderr.write(f"{PACKAGE_NAME}: {error}\n")
        return EXIT_FAILURE
    except KeyboardInterrupt:
        return EXIT_FAILURE
