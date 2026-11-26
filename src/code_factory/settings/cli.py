"""`code-factory config check|show`, `docs --out DIR` and `intake-key list|revoke`."""

import argparse
import importlib
import json
import sys
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from code_factory.platform.db import Base, describe_tables
from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.module import Command, Module
from code_factory.platform.services import Services
from code_factory.settings.models.config import RepositoryConfig
from code_factory.settings.models.modules import (
    ColumnFacts,
    CommandFacts,
    ModuleFacts,
    TableFacts,
)
from code_factory.settings.rules import (
    render_commands_page,
    render_config_page,
    render_feature_map_page,
    render_modules_page,
    render_tables_page,
)
from code_factory.settings.service import SettingsService

EXIT_PROBLEMS = 1
EXIT_USAGE = 2


def _configure_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=["check", "show"],
        help="check: report each defect as path:line: message; show: the config as JSON",
    )
    parser.add_argument(
        "path", nargs="?", default=".", help="the repository, default the current one"
    )


async def _run_config(args: argparse.Namespace, services: Services) -> int:
    settings = services.get(SettingsService)
    if args.action == "show":
        config = await settings.load(await settings.main_checkout(Path(args.path)))
        sys.stdout.write(
            json.dumps(config.model_dump(mode="json", exclude_none=True), indent=2) + "\n"
        )
        return 0
    report = await settings.check_repository(await settings.repository_root(Path(args.path)))
    for problem in report.problems:
        sys.stdout.write(f"{problem}\n")
    for note in report.notes:
        sys.stderr.write(f"{note}\n")
    if report.unchecked:
        sys.stderr.write(
            f"not checked: {', '.join(report.unchecked)} (the tickets module is not bound)\n"
        )
    return EXIT_PROBLEMS if report.problems else 0


def _configure_docs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--out",
        required=True,
        help=(
            "the folder to write commands.md, config.md, modules.md, feature-map.md and"
            " database-tables.md into"
        ),
    )


def _tables_by_module() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for mapper in Base.registry.mappers:
        owner = mapper.class_.__module__.split(".")[1]
        found.setdefault(owner, []).append(str(getattr(mapper.local_table, "name", "")))
    return found


def _route_lines(routes: Iterable[object]) -> list[str]:
    """`METHOD path` of each route, an included router's routes in its place."""
    lines: list[str] = []
    for route in routes:
        included = getattr(route, "effective_route_contexts", None)
        if callable(included):
            lines += _route_lines(included())
            continue
        methods = getattr(route, "methods", None)
        if isinstance(methods, (set, frozenset)):
            verbs = " ".join(sorted(str(m) for m in methods if m != "HEAD"))
            lines.append(f"{verbs} {getattr(route, 'path', '')}")
    return lines


def _facts(module: Module) -> ModuleFacts:
    package = importlib.import_module(f"code_factory.{module.name}")
    summary = next(iter((package.__doc__ or "").strip().splitlines()), "")
    routes = _route_lines(module.router.routes if module.router is not None else [])
    return ModuleFacts(
        name=module.name,
        summary=summary,
        routes=tuple(routes),
        commands=tuple(CommandFacts(command.name, command.help) for command in module.commands),
        tools=module.register_tools is not None,
        background=module.background is not None,
        tables=tuple(sorted(_tables_by_module().get(module.name, []))),
    )


def _table_facts(modules: Iterable[Module]) -> list[TableFacts]:
    """The platform's tables, then each module's in the order of `modules`.

    Within an owner, tables keep the order they are defined in.
    """
    found: dict[str, list[TableFacts]] = {"platform": [], **{m.name: [] for m in modules}}
    for shape in describe_tables():
        if shape.owner in found:
            columns = tuple(ColumnFacts(**asdict(column)) for column in shape.columns)
            found[shape.owner].append(TableFacts(shape.name, shape.owner, shape.summary, columns))
    return [table for tables in found.values() for table in tables]


def _run_docs(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.exists() and not out.is_dir():
        sys.stderr.write(f"code-factory: {out} is not a folder\n")
        return EXIT_USAGE
    pages = {"config.md": render_config_page(RepositoryConfig)}
    root_parser = getattr(args, "root_parser", None)
    if root_parser is not None:
        pages = {"commands.md": render_commands_page(root_parser), **pages}
    modules = getattr(args, "modules", ())
    if modules:
        facts = [_facts(module) for module in modules]
        pages["modules.md"] = render_modules_page(facts)
        pages["feature-map.md"] = render_feature_map_page(facts)
        pages["database-tables.md"] = render_tables_page(_table_facts(modules))
    else:
        sys.stderr.write(
            "code-factory: commands.md not written: the root parser is not available\n"
        )
    out.mkdir(parents=True, exist_ok=True)
    for name, text in pages.items():
        (out / name).write_text(text, encoding="utf-8")
        sys.stdout.write(f"{out / name}\n")
    return 0


def _configure_intake_key(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["list", "revoke"], help="list the grants or delete one")
    parser.add_argument(
        "name", nargs="?", help="revoke: the key name, for example CODE_FACTORY_INTAKE_JIRA"
    )


async def _run_intake_key(args: argparse.Namespace, services: Services) -> int:
    settings = services.get(SettingsService)
    if args.action == "list":
        sys.stdout.write("KEY  REPOSITORY  URL\n")
        for grant in await settings.list_intake_grants():
            sys.stdout.write(f"{grant.key_name}  {grant.repository}  {grant.url}\n")
        return 0
    if not args.name:
        raise BadRequestError(
            "revoke needs the key name; `code-factory intake-key list` shows them"
        )
    if not await settings.revoke_intake_key(args.name):
        msg = f"no grant for {args.name}; `code-factory intake-key list` shows them"
        raise NotFoundError(msg)
    sys.stdout.write(f"revoked {args.name}\n")
    return 0


config_command = Command(
    "config",
    "check or show a repository's .code-factory/config.toml",
    configure=_configure_config,
    run_async=_run_config,
)
docs_command = Command(
    "docs",
    "write the reference pages of the commands, settings, modules and tables",
    configure=_configure_docs,
    run=_run_docs,
)
intake_key_command = Command(
    "intake-key",
    "list or revoke the repository and address each tracker key may serve",
    configure=_configure_intake_key,
    run_async=_run_intake_key,
)
