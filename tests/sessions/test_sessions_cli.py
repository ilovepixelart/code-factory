"""`code-factory sessions [list|ingest|rebuild]`."""

import argparse
import json

import pytest
from sample_world import World
from sessions_values import answer

from code_factory.platform.services import Services
from code_factory.sessions.cli import sessions_command
from code_factory.sessions.service import SessionService

pytestmark = pytest.mark.usefixtures("sample")


def parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sessions")
    sessions_command.configure(parser)
    return parser.parse_args(argv)


@pytest.fixture
def services(sessions: SessionService) -> Services:
    registry = Services()
    registry.add(SessionService, sessions)
    return registry


async def run(services: Services, *argv: str) -> int:
    run_async = sessions_command.run_async
    assert run_async is not None
    return await run_async(parse(*argv), services)


async def test_ingest_says_how_many_lines_and_rejects_it_took(
    services: Services, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await run(services, "ingest") == 0
    assert capsys.readouterr().out == "45 lines, 2 rejects\n"
    assert await run(services, "ingest") == 0
    assert capsys.readouterr().out == "0 lines, 0 rejects\n"


@pytest.mark.parametrize("argv", [(), ("list",)])
async def test_listing_prints_every_session_as_indented_json_after_an_ingest(
    services: Services, capsys: pytest.CaptureFixture[str], world: World, argv: tuple[str, ...]
) -> None:
    assert await run(services, *argv) == 0
    out = capsys.readouterr().out
    assert out.startswith('[\n  {\n    "session_id": "s-block"')
    assert out.endswith("]\n")
    expected = json.loads(world.real(json.dumps(answer("/api/sessions")["body"])))
    shown = json.loads(out)
    assert [row["session_id"] for row in shown] == [row["session_id"] for row in expected]


async def test_rebuild_says_how_many_sessions_it_derived_again(
    services: Services, capsys: pytest.CaptureFixture[str]
) -> None:
    await run(services, "ingest")
    capsys.readouterr()
    assert await run(services, "rebuild") == 0
    assert capsys.readouterr().out == "10\n"
