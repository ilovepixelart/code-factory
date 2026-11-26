"""Tracked repositories through the service, against the test database."""

from pathlib import Path

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.repositories.models import RepositoryRecord
from code_factory.repositories.service import RepositoryService

SAMPLE = Path("/srv/code/sample")


async def test_a_tracked_repository_is_listed_with_its_folder_name_and_root(
    repositories: RepositoryService,
) -> None:
    tracked = await repositories.track(SAMPLE)
    assert tracked == RepositoryRecord(name="sample", path="/srv/code/sample")
    assert await repositories.list() == [tracked]


async def test_nothing_is_listed_before_a_repository_is_tracked(
    repositories: RepositoryService,
) -> None:
    assert await repositories.list() == []


async def test_the_list_is_ordered_by_name(repositories: RepositoryService) -> None:
    for root in ("/srv/code/zeta", "/srv/code/alpha", "/srv/code/mid"):
        await repositories.track(Path(root))
    assert [record.name for record in await repositories.list()] == ["alpha", "mid", "zeta"]


async def test_get_answers_the_root_of_a_name(repositories: RepositoryService) -> None:
    await repositories.track(SAMPLE)
    assert await repositories.get("sample") == SAMPLE


async def test_get_refuses_an_unknown_name_with_the_sentence_the_app_expects(
    repositories: RepositoryService,
) -> None:
    with pytest.raises(NotFoundError, match=r"^unknown repository$"):
        await repositories.get("nothing")


async def test_tracking_a_path_twice_is_a_no_op(repositories: RepositoryService) -> None:
    first = await repositories.track(SAMPLE)
    again = await repositories.track(Path("/srv/code/sample/"))
    assert again == first
    assert await repositories.list() == [first]


async def test_a_second_folder_with_the_same_name_conflicts(
    repositories: RepositoryService,
) -> None:
    await repositories.track(SAMPLE)
    with pytest.raises(
        ConflictError, match=r"^a repository named sample is tracked already at /srv/code/sample$"
    ):
        await repositories.track(Path("/elsewhere/sample"))
    assert [record.path for record in await repositories.list()] == ["/srv/code/sample"]


async def test_a_relative_path_is_not_tracked(repositories: RepositoryService) -> None:
    with pytest.raises(BadRequestError, match="is not an absolute path"):
        await repositories.track(Path("sample"))
    assert await repositories.list() == []


async def test_untrack_removes_the_repository_and_says_so(
    repositories: RepositoryService,
) -> None:
    await repositories.track(SAMPLE)
    assert await repositories.untrack(SAMPLE) is True
    assert await repositories.list() == []
    with pytest.raises(NotFoundError):
        await repositories.get("sample")


async def test_untracking_a_path_that_is_not_tracked_is_false(
    repositories: RepositoryService,
) -> None:
    await repositories.track(SAMPLE)
    assert await repositories.untrack(Path("/elsewhere/sample")) is False
    assert [record.name for record in await repositories.list()] == ["sample"]


async def test_a_name_can_be_tracked_again_after_untracking(
    repositories: RepositoryService,
) -> None:
    await repositories.track(SAMPLE)
    await repositories.untrack(SAMPLE)
    moved = await repositories.track(Path("/elsewhere/sample"))
    assert moved.path == "/elsewhere/sample"
