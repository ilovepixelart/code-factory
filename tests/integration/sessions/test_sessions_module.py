"""The module as the app runs it: its tasks, from the hook to the stream."""

import asyncio
import contextlib
import json
import shlex
from pathlib import Path
from typing import cast

from code_factory.app import build_resources, build_services
from code_factory.platform.config import Settings
from code_factory.sessions.models import AtWork as SessionAtWork
from code_factory.sessions.module import TeamSessions, module
from code_factory.sessions.service import SessionService
from code_factory.team.models import AtWork as TeamAtWork
from sessions_harness import Committed


async def test_the_module_registers_its_service_and_starts_three_named_tasks(
    settings: Settings, tmp_path: Path
) -> None:
    resources = build_resources(settings.model_copy(update={"state_dir": tmp_path}))
    services = build_services(resources, [module])
    assert services.get(SessionService) is not None
    assert module.background is not None
    try:
        async with resources.tasks.run():
            module.background(services, resources.tasks)
            assert sorted(resources.tasks.names) == [
                "sessions.ingest",
                "sessions.listen",
                "sessions.maintenance",
            ]
            services.get(SessionService).shutdown()
    finally:
        await resources.engine.dispose()
    assert resources.tasks.names == []


async def test_a_payload_the_hook_records_reaches_an_open_stream_through_the_running_tasks(
    settings: Settings, committed: Committed, tmp_path: Path
) -> None:
    resources = build_resources(settings.model_copy(update={"state_dir": tmp_path}))
    services = build_services(resources, [module])
    service = services.get(SessionService)
    hook = shlex.split(service.capture_hook().command)
    stop = asyncio.Event()
    try:
        async with resources.tasks.run():
            assert module.background is not None
            module.background(services, resources.tasks)
            frames = service.event_stream(0, stop)

            async def next_frame() -> str:
                return await anext(frames)

            first = asyncio.create_task(next_frame())
            await asyncio.sleep(0.5)  # the listener is up and the stream is open
            process = await asyncio.create_subprocess_exec(
                *hook,
                stdin=asyncio.subprocess.PIPE,
                env={"CODE_FACTORY_STATE_DIR": str(tmp_path)},
            )
            async with asyncio.timeout(20):
                await process.communicate(b'{"session_id": "e2e", "hook_event_name": "Stop"}')
            async with asyncio.timeout(5):
                frame = await first
            stop.set()
            with contextlib.suppress(StopAsyncIteration):
                await frames.aclose()  # ty: ignore[missing-attribute]  # an async generator
    finally:
        await resources.engine.dispose()
    data = json.loads(frame.split("data: ", 1)[1])
    assert (data["session_id"], data["event"]) == ("e2e", "Stop")
    assert committed.admin is not None


class _Sessions:
    """The one read the team's port makes of the sessions service."""

    def __init__(self, found: list[SessionAtWork]) -> None:
        self.found = found

    async def subagents_at_work(self) -> list[SessionAtWork]:
        return self.found


async def test_the_team_reads_each_subagent_at_work_on_a_ticket() -> None:
    working = SessionAtWork(
        ticket="CF-7",
        session_id="s1",
        agent_id="a1b2c3d4",
        name="reviewer a1b2",
        kind="reviewer",
        doing="Read src/app.py",
        since=100.0,
        last_event_at=160.0,
    )
    port = TeamSessions(cast("SessionService", _Sessions([working])))

    assert await port.subagents_at_work() == [
        TeamAtWork(
            agent_id="a1b2c3d4",
            ticket_id="CF-7",
            kind="reviewer",
            name="reviewer a1b2",
            doing="Read src/app.py",
            since=100.0,
            last_event_at=160.0,
        )
    ]
