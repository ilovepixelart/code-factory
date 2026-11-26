"""`Served` (what this process serves) and the `serve` command a module may provide."""

import argparse
import sys
from functools import partial

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app_lifespan import IDLE_MODULES, running_lifespan
from code_factory import app as composition_root
from code_factory.app import build_resources, build_services, create_app
from code_factory.platform import cli
from code_factory.platform.config import Settings
from code_factory.platform.module import Command, Module
from code_factory.platform.served import Served

SERVED = Served(
    address="127.0.0.1", port=4999, both_loopbacks=True, base_url="http://localhost:4999"
)


def test_a_process_that_does_not_serve_has_no_address_and_no_link() -> None:
    none = Served.none()
    assert (none.address, none.port, none.both_loopbacks, none.base_url) == ("", 0, False, "")
    assert not none.serving
    assert SERVED.serving


def test_each_served_has_its_own_stopping_signal_which_is_not_part_of_its_value() -> None:
    first, second = Served.none(), Served.none()
    first.stopping.set()
    assert not second.stopping.is_set()
    assert first == second


def test_every_process_gets_a_served_from_the_services(offline_settings: Settings) -> None:
    resources = build_resources(offline_settings)
    assert build_services(resources, []).get(Served) == Served.none()
    assert build_services(resources, [], served=SERVED).get(Served) is SERVED


def test_the_app_registers_the_served_it_was_given(offline_settings: Settings) -> None:
    app = create_app(offline_settings, served=SERVED)
    assert app.state.services.get(Served) is SERVED


async def get_health(settings: Settings, served: Served | None, host: str) -> int:
    app = create_app(settings, served=served)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        return (await client.get("/api/health", headers={"host": host})).status_code


async def test_the_host_guard_follows_the_served_port(offline_settings: Settings) -> None:
    assert offline_settings.port == 4000
    assert await get_health(offline_settings, SERVED, "localhost:4999") == 200
    assert await get_health(offline_settings, SERVED, "localhost:4000") == 400


async def test_the_host_guard_follows_the_settings_port_when_nothing_is_served(
    offline_settings: Settings,
) -> None:
    assert await get_health(offline_settings, None, "localhost:4000") == 200
    assert await get_health(offline_settings, None, "localhost:4999") == 400


def _serving_module(name: str, ran: list[str]) -> Module:
    def serve_command(create_app: object) -> Command:
        def run(_args: argparse.Namespace) -> int:
            ran.append(f"{name} with {create_app is composition_root.create_app}")
            sys.stdout.write(f"{name} serves\n")
            return 5

        return Command("serve", "serve, the module's way", run=run)

    return Module(name=name, serve_command=serve_command)


def _main(*modules: Module, argv: list[str]) -> int:
    return cli.main(
        argv,
        create_app=composition_root.create_app,
        create_mcp=composition_root.create_mcp_server,
        open_services=partial(composition_root.open_services, modules=list(modules)),
        modules=list(modules),
    )


def test_a_module_provides_the_serve_command_with_the_app_factory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ran: list[str] = []
    assert _main(_serving_module("serving", ran), argv=["serve"]) == 5
    assert ran == ["serving with True"]
    assert capsys.readouterr().out == "serving serves\n"


def test_the_other_platform_commands_are_untouched_by_a_serving_module(
    capsys: pytest.CaptureFixture[str],
) -> None:
    given = _serving_module("serving", [])
    with pytest.raises(SystemExit) as raised:
        _main(given, argv=["--help"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    assert "serve, the module's way" in out
    assert "serve the API, Swagger UI and MCP over HTTP" not in out
    assert "serve the MCP server over stdio" in out


def test_two_modules_cannot_both_provide_serve() -> None:
    given = _serving_module("first", [])
    given_2 = _serving_module("second", [])
    with pytest.raises(ValueError, match="serve is provided by both first and second"):
        _main(given, given_2, argv=["serve"])


async def test_the_startup_sign_in_link_names_the_bound_listener(
    settings: Settings,
    connection: object,
    migrated: None,  # noqa: ARG001
) -> None:
    factory = async_sessionmaker(
        bind=connection,  # ty: ignore[invalid-argument-type]
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    app = create_app(settings, factory, served=SERVED, modules=IDLE_MODULES)
    async with running_lifespan(app):
        assert app.state.startup_lines[0].startswith("sign in: http://localhost:4999/owner/")
