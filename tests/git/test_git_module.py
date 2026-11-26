"""The module probes this machine's git when the application starts."""

import asyncio
import logging
from typing import cast

import pytest

from code_factory.git.module import build_module
from code_factory.git.service import GitPorts, GitService
from code_factory.platform.background import background_tasks
from code_factory.platform.errors import UnavailableError
from code_factory.platform.services import Services


class _Probed:
    def __init__(self, *, fails: bool) -> None:
        self.fails = fails
        self.calls = 0

    async def probe(self) -> None:
        self.calls += 1
        if self.fails:
            msg = "this git cannot run the board's merge checks; install git 2.38 or later"
            raise UnavailableError(msg)


def _no_ports(_services: Services) -> GitPorts:
    msg = "the probe needs no ports"
    raise AssertionError(msg)


async def _start(probed: _Probed) -> None:
    module = build_module(_no_ports)
    services = Services()
    services.add(GitService, cast("GitService", probed))
    assert module.background is not None
    async with background_tasks() as tasks:
        module.background(services, tasks)
        started = [t for t in asyncio.all_tasks() if t.get_name() == "git-probe"]
        assert len(started) == 1
        await asyncio.wait(started)


async def test_startup_runs_the_probe() -> None:
    probed = _Probed(fails=False)
    await _start(probed)
    assert probed.calls == 1


async def test_a_git_that_cannot_run_the_probe_is_reported_at_startup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        await _start(_Probed(fails=True))
    assert "background task git-probe failed" in caplog.text
    assert "install git 2.38 or later" in caplog.text
