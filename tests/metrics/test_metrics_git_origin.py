"""The origin address: no answer is a fact only when git says there is no GitHub origin."""

from pathlib import Path
from typing import override

import pytest
from test_metrics_git_reader import shim

from code_factory.metrics.adapters import GitReader, GitUnavailableError
from code_factory.metrics.service import MetricsService
from git_support import git, make_repo
from metrics_support import HOUR, NOW, World, pull_request


async def test_a_repository_with_no_origin_remote_has_no_address(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    git(root, "remote", "remove", "origin")
    assert await GitReader().origin_web(root) is None


async def test_a_call_over_its_time_is_unavailable_not_an_absent_address(tmp_path: Path) -> None:
    reader = GitReader(str(shim(tmp_path, "sleep 30")), origin_timeout_s=0.3)
    with pytest.raises(GitUnavailableError, match="origin"):
        await reader.origin_web(tmp_path / "repo")


async def test_a_path_that_is_not_a_repository_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(GitUnavailableError, match="origin"):
        await GitReader().origin_web(tmp_path)


class FlakyOrigin(GitReader):
    """The first question to git fails, the next answers."""

    def __init__(self) -> None:
        super().__init__()
        self.asked = 0

    @override
    async def origin_web(self, root: Path) -> str | None:
        self.asked += 1
        if self.asked == 1:
            msg = "cannot read the origin of sample: it took more than 10 s"
            raise GitUnavailableError(msg)
        return "https://github.com/o/r"


async def test_a_failed_lookup_of_the_address_is_asked_again_by_the_next_read(
    world: World, root: Path, uow: object
) -> None:
    metrics: MetricsService = world.service(uow, FlakyOrigin())  # ty: ignore[invalid-argument-type]
    pull_request(root, 7, "ticket/cf-1", NOW - HOUR)
    await metrics.refresh()

    [first] = (await metrics.flow()).merged
    [second] = (await metrics.flow()).merged

    assert (first.url, second.url) == (None, "https://github.com/o/r/pull/7")
