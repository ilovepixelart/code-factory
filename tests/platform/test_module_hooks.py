"""`Module.background` and `Resources.on_stop`: what a module may start and stop with the app."""

import asyncio

import pytest

from app_lifespan import running_lifespan
from code_factory.app import (
    MODULES,
    build_resources,
    build_services,
    create_mcp_server,
    open_services,
)
from code_factory.auth.service import AuthService
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.config import Settings
from code_factory.platform.mcp import Access
from code_factory.platform.module import Module, Resources
from code_factory.platform.runtime import running
from code_factory.platform.services import Services
from code_factory.platform.web.app import create_web_app


class Probe:
    """A service the probe module registers and its background task reads."""

    def __init__(self) -> None:
        self.ticks = asyncio.Event()


def probe_module() -> Module:
    def provide(services: Services, _resources: Resources) -> None:
        services.add(Probe, Probe())

    def background(services: Services, tasks: BackgroundTasks) -> None:
        probe = services.get(Probe)

        async def tick() -> None:
            probe.ticks.set()
            await asyncio.Event().wait()

        tasks.start("probe-tick", tick)

    return Module(name="probe", provide=provide, background=background)


async def test_the_app_lifespan_runs_every_modules_background_hook_and_cancels_it_at_shutdown(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    modules = (*MODULES, probe_module())
    resources = build_resources(settings)
    services = build_services(resources, modules)
    app = create_web_app(
        resources,
        services=services,
        modules=modules,
        mcp_access=Access(verifier=services.get(AuthService)),
    )
    async with running_lifespan(app):
        await asyncio.wait_for(services.get(Probe).ticks.wait(), timeout=2)
        task = next(t for t in asyncio.all_tasks() if t.get_name() == "probe-tick")
        assert not task.done()
    assert task.cancelled()


async def test_a_command_and_the_stdio_mcp_server_start_no_module_background_work(
    settings: Settings,
    migrated: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[str] = []

    def background(_services: Services, tasks: BackgroundTasks) -> None:
        started.append("background")

        async def forever() -> None:
            await asyncio.Event().wait()

        tasks.start("never", forever)

    watching = Module(name="watching", background=background)
    monkeypatch.setenv("CODE_FACTORY_MCP_TOKEN", "not-checked-until-a-call")
    create_mcp_server(settings, (*MODULES, watching))
    async with open_services(settings, (*MODULES, watching)):
        assert started == []
        assert [t for t in asyncio.all_tasks() if t.get_name() == "never"] == []


async def test_on_stop_hooks_run_in_order_while_background_tasks_still_run(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    resources = build_resources(settings)
    seen: list[str] = []

    async def first() -> None:
        seen.append(f"first, tasks running: {resources.tasks.names}")

    async def second() -> None:
        seen.append("second")

    async def forever() -> None:
        await asyncio.Event().wait()

    resources.on_stop.extend([first, second])
    async with running(resources) as tasks:
        tasks.start("worker", forever)
    assert seen == ["first, tasks running: ['worker']", "second"]


async def test_a_failing_on_stop_hook_is_logged_and_the_next_one_still_runs(
    settings: Settings,
    migrated: None,  # noqa: ARG001
    caplog: pytest.LogCaptureFixture,
) -> None:
    resources = build_resources(settings)
    ran: list[str] = []

    async def fails() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    async def after() -> None:
        ran.append("after")

    resources.on_stop.extend([fails, after])
    async with running(resources):
        pass
    assert ran == ["after"]
    assert "on_stop hook fails failed" in caplog.text
