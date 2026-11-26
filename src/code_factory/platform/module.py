"""What a domain module hands to the platform, and what the platform hands back to build it.

A module's `module.py` builds one `Module`; `code_factory.app` lists them. The platform reads only
these descriptions, so adding a module changes no platform file. The framework types appear under
`TYPE_CHECKING` only: this file imports neither FastAPI nor FastMCP at run time.
"""

import argparse
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from code_factory.platform.background import BackgroundTasks
from code_factory.platform.config import Settings
from code_factory.platform.db import AsyncEngine, UnitOfWork
from code_factory.platform.services import Services

if TYPE_CHECKING:
    from fastapi import APIRouter
    from fastmcp import FastMCP


@dataclass(frozen=True)
class Resources:
    """What a module's service may be built from; `tasks` starts work once the app runs.

    `on_stop` is a list a module appends to in `provide`: each awaitable runs once, in order, when
    the app stops and before the background tasks are cancelled, so work that must finish first
    (draining running checks) still has its tasks. A hook bounds its own wait; a failing one is
    logged and the rest still run.
    """

    settings: Settings
    engine: AsyncEngine
    uow: UnitOfWork
    tasks: BackgroundTasks
    on_stop: list[Callable[[], Awaitable[None]]] = field(default_factory=list)


@dataclass(frozen=True)
class Command:
    """A CLI subcommand: `code-factory <name> ...`.

    `configure` adds arguments to the subparser. Exactly one of two runners: `run(args)` for a
    command that needs no database, or `run_async(args, services)` for one that uses the modules'
    services, called on a started runtime (schema checked, unit of work ready). Either returns
    the exit code. An expected failure is raised as a `CodeFactoryError`, which prints one
    sentence and exits 1.
    """

    name: str
    help: str
    run: Callable[[argparse.Namespace], int] | None = None
    configure: Callable[[argparse.ArgumentParser], None] = lambda _parser: None
    run_async: Callable[[argparse.Namespace, Services], Awaitable[int]] | None = None
    # For a `run_async` command: runs first on the settings, before any connection, and raises a
    # `CodeFactoryError` to refuse.
    check: Callable[[Settings], None] | None = None

    def __post_init__(self) -> None:
        """Refuse a command with no runner or with both."""
        if (self.run is None) == (self.run_async is None):
            msg = f"command {self.name} needs exactly one of run and run_async"
            raise ValueError(msg)


@dataclass(frozen=True)
class Module:
    """One domain module as the platform sees it. Every field but `name` is optional."""

    name: str
    # Called once at startup, in the order of `app.MODULES`: build the module's service from
    # `resources` and register it with `services.add(Class, instance)`.
    provide: Callable[[Services, Resources], None] | None = None
    # Mounted on the HTTP app.
    router: APIRouter | None = None
    # Called once to add the module's tools to the MCP server: `register_tools(mcp, services)`.
    register_tools: Callable[[FastMCP, Services], None] | None = None
    # At most one module provides it. Called with the app factory (`create_app(settings, *,
    # served=None)`) to build the `serve` command in place of the platform's plain one.
    serve_command: Callable[[Callable[..., object]], Command] | None = None
    commands: tuple[Command, ...] = ()
    # Called once when the HTTP app starts, after the schema check and every module's `provide`
    # (not for the stdio MCP server or a CLI command): start the module's long-lived work with
    # `tasks.start(name, work)`.
    background: Callable[[Services, BackgroundTasks], None] | None = None
