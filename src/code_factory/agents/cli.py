"""The agents module's commands: `agents`, `connections` and `secret`."""

import argparse
import sys
from pathlib import Path

from code_factory.agents.adapters.credentials import KEY_NAME
from code_factory.agents.service import AgentService
from code_factory.platform.errors import BadRequestError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.settings.service import SettingsService

INTAKE_PREFIX = "CODE_FACTORY_INTAKE_"
FAILED = 1


def _line(*cells: str) -> str:
    return "  ".join(cells).rstrip() + "\n"


def _configure_agents(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["list", "check"], help="list the agents or test a model")
    parser.add_argument("name", nargs="?", help="check: the agent's name")


async def _run_agents(args: argparse.Namespace, services: Services) -> int:
    agents = services.get(AgentService)
    if args.action == "check":
        if not args.name:
            msg = "check needs the agent's name; `code-factory agents list` shows them"
            raise BadRequestError(msg)
        result = await agents.check_model(args.name)
        if result.passed:
            sys.stdout.write(f"{args.name}: {result.model} passed its model check\n")
            return 0
        sys.stdout.write(f"{args.name}: {result.problem}\n")
        return FAILED
    listed = await agents.list_definitions()
    sys.stdout.write(_line("NAME", "RUNTIME", "CONNECTION", "MODEL", "COLUMNS", "PAUSED", "CHECK"))
    for agent in listed.agents:
        check = listed.checks.get(agent.name)
        state = "" if check is None else ("passed" if check.passed else check.problem)
        sys.stdout.write(
            _line(
                agent.name,
                agent.runtime,
                agent.connection or "-",
                agent.model or "-",
                ",".join(agent.roles) or "-",
                "yes" if agent.paused_at is not None else "no",
                state,
            )
        )
    return 0


def _configure_connections(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["list", "status"], help="list them or ask each")


async def _run_connections(args: argparse.Namespace, services: Services) -> int:
    agents = services.get(AgentService)
    if args.action == "list":
        await _list_connections(agents)
    else:
        await _connection_status(agents)
    return 0


async def _list_connections(agents: AgentService) -> None:
    sys.stdout.write(_line("NAME", "KIND", "ADDRESS", "KEY"))
    for view in (await agents.list_connections()).connections:
        key = "-" if not view.connection.key_env else ("set" if view.key_set else "not set")
        sys.stdout.write(
            _line(view.connection.name, view.connection.kind, view.connection.base_url, key)
        )


async def _connection_status(agents: AgentService) -> None:
    status = await agents.connection_status()
    sys.stdout.write(_line("NAME", "ANSWERS", "MODELS", "PROBLEM"))
    for found in status.connections:
        models = ",".join(model.id for model in found.models) or "-"
        sys.stdout.write(_line(found.name, "yes" if found.answers else "no", models, found.problem))
    for local in status.local:
        sys.stdout.write(_line("local", local.kind, local.base_url, local.state))


def _configure_secret(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["set", "status", "remove"])
    parser.add_argument("name", help="the key's name, for example ANTHROPIC_API_KEY")
    parser.add_argument("--repository", help="set: the repository an intake key serves")
    parser.add_argument("--url", help="set: the tracker address an intake key goes to")


def _check_intake_options(name: str, repository: str | None, url: str | None) -> None:
    if not name.startswith(INTAKE_PREFIX):
        if repository is not None or url is not None:
            msg = f"only an intake key ({INTAKE_PREFIX}...) is stored with --repository and --url"
            raise BadRequestError(msg)
        return
    if repository is None or url is None:
        msg = (
            f"{name} is an intake key: name the repository it serves with --repository "
            "and its tracker's address with --url"
        )
        raise BadRequestError(msg)


async def _restore_grant(
    settings: SettingsService, name: str, before: tuple[str, str] | None, *, granted: bool
) -> None:
    """Put the grant back as it was before a key was stored: the old key keeps its scope."""
    if not granted:
        return
    if before is None:
        await settings.revoke_intake_key(name)
    else:
        await settings.grant_intake_key(name, Path(before[0]), before[1])


async def _run_secret(args: argparse.Namespace, services: Services) -> int:
    agents = services.get(AgentService)
    name = str(args.name)
    if KEY_NAME.fullmatch(name) is None:
        msg = "a key name is capitals, digits and _"
        raise BadRequestError(msg)
    if args.action == "status":
        sys.stdout.write("set\n" if await agents.key_set(name) else "not set\n")
        return 0
    if args.action == "remove":
        sys.stdout.write("removed\n" if await agents.forget_key(name) else "not in the store\n")
        return 0
    _check_intake_options(name, args.repository, args.url)
    settings = services.get(SettingsService)
    found = await settings.intake_grant(name)
    prior = None if found is None else (found.repository, found.url)
    if args.repository is not None:
        await settings.grant_intake_key(name, Path(args.repository), args.url)
    try:
        code = await agents.store_key(name)
    except BaseException:
        await _restore_grant(settings, name, prior, granted=args.repository is not None)
        raise
    if code != 0:
        await _restore_grant(settings, name, prior, granted=args.repository is not None)
        return code
    sys.stdout.write(f"{name} stored\n")
    return 0


agents_command = Command(
    "agents",
    "list the agents or test an agent's model",
    configure=_configure_agents,
    run_async=_run_agents,
)
connections_command = Command(
    "connections",
    "list the model connections or ask each whether it answers",
    configure=_configure_connections,
    run_async=_run_connections,
)
secret_command = Command(
    "secret",
    "set, test or remove a provider key in the operating system's credential store",
    configure=_configure_secret,
    run_async=_run_secret,
)
