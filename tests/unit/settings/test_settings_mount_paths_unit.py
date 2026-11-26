"""A checks container mount is judged by the folder it reaches on disk, not by its spelling: a
doubled slash, a link or another case of a secret folder is refused, an unrelated folder is not."""

import threading
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

import pytest

from code_factory.settings.adapters import RESOLVE_WORKERS, local_resolver
from code_factory.settings.adapters import resolver as resolver_module
from code_factory.settings.rules.secrets import (
    VALIDATION_HOME,
    container_mount_problem,
    mount_reaches_secrets,
)


@pytest.fixture(autouse=True)
def _workers_idle() -> Iterator[None]:
    """The resolver worker budget is the process's: wait for abandoned workers to end."""
    yield
    for _ in range(RESOLVE_WORKERS):
        assert resolver_module._SLOTS.acquire(timeout=5)
    for _ in range(RESOLVE_WORKERS):
        resolver_module._SLOTS.release()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    found = tmp_path / "home" / "alex"
    (found / ".ssh").mkdir(parents=True)
    (found / "work").mkdir()
    return found


class Recorder:
    """A resolver that records what it is asked and changes nothing."""

    def __init__(self) -> None:
        self.calls: list[PurePosixPath] = []

    def __call__(self, path: PurePosixPath) -> PurePosixPath:
        self.calls.append(path)
        return path


@pytest.mark.parametrize("host", ["/srv/a\x00b", "/srv/a\nb", "/srv/a\x1bb", "/srv/a\x7fb"])
def test_a_host_path_with_a_control_character_is_refused_before_it_is_resolved(host: str) -> None:
    recorder = Recorder()
    problem = container_mount_problem(f"{host}:/x", (VALIDATION_HOME,), recorder)
    assert problem == f"{host}:/x: the host folder holds a control character"
    assert recorder.calls == []


def test_a_path_that_cannot_be_resolved_reaches_the_secrets(tmp_path: Path) -> None:
    resolve = local_resolver((PurePosixPath(tmp_path),))
    assert mount_reaches_secrets(
        PurePosixPath(tmp_path / "a\x00b"), PurePosixPath(tmp_path / "home"), resolve
    )


@pytest.mark.parametrize("host", ["/net/host/x", "/Volumes/disk", "/mnt/share/a", "/Network/x"])
def test_a_mount_on_an_automount_root_is_refused_without_being_resolved(host: str) -> None:
    recorder = Recorder()
    problem = container_mount_problem(f"{host}:/x", (VALIDATION_HOME,), recorder)
    assert problem == f"{host}:/x: the host folder is on a network or automounted volume"
    assert recorder.calls == []


def test_a_folder_that_only_looks_like_an_automount_root_is_accepted() -> None:
    assert container_mount_problem("/netfs/x:/x", (VALIDATION_HOME,), Recorder()) is None
    assert container_mount_problem("/srv/mnt:/x", (VALIDATION_HOME,), Recorder()) is None


def test_a_resolution_that_outlasts_its_timeout_fails_closed(tmp_path: Path) -> None:
    release = threading.Event()

    def stuck(path: str) -> str:
        release.wait(5)
        return path

    resolve = local_resolver((PurePosixPath(tmp_path),), timeout=0.05, follow=stuck)
    try:
        assert resolve(PurePosixPath(tmp_path / "a")) == PurePosixPath("/")
    finally:
        release.set()


def test_only_paths_below_a_local_root_are_resolved(tmp_path: Path) -> None:
    asked: list[str] = []

    def follow(path: str) -> str:
        asked.append(path)
        return path

    resolve = local_resolver((PurePosixPath(tmp_path),), follow=follow)
    inside = PurePosixPath(tmp_path / "x")
    assert resolve(inside) == inside
    assert resolve(PurePosixPath("/srv/elsewhere")) == PurePosixPath("/srv/elsewhere")
    assert asked == [str(inside)]


def test_resolutions_stuck_on_a_dead_mount_are_capped_and_then_fail_closed(tmp_path: Path) -> None:
    release = threading.Event()
    started: list[str] = []

    def stuck(path: str) -> str:
        started.append(path)
        release.wait(5)
        return path

    resolve = local_resolver((PurePosixPath(tmp_path),), timeout=0.01, follow=stuck)
    try:
        for index in range(RESOLVE_WORKERS + 3):
            assert resolve(PurePosixPath(tmp_path / str(index))) == PurePosixPath("/")
        assert len(started) == RESOLVE_WORKERS
    finally:
        release.set()


def test_a_slot_is_free_again_once_its_resolution_ends(tmp_path: Path) -> None:
    resolve = local_resolver((PurePosixPath(tmp_path),), follow=lambda path: path)
    inside = PurePosixPath(tmp_path / "x")
    assert [resolve(inside) for _ in range(RESOLVE_WORKERS * 3)] == [inside] * RESOLVE_WORKERS * 3


def test_a_root_is_recognised_in_another_case(tmp_path: Path) -> None:
    asked: list[str] = []

    def follow(path: str) -> str:
        asked.append(path)
        return path

    resolve = local_resolver((PurePosixPath(tmp_path),), follow=follow)
    resolve(PurePosixPath(str(tmp_path).upper()) / "x")
    assert len(asked) == 1


def test_every_expanded_host_is_held_off_an_automount_root() -> None:
    homes = (VALIDATION_HOME, PurePosixPath("/net/u/alex"))
    recorder = Recorder()
    problem = container_mount_problem("~/cache:/x", homes, recorder)
    assert problem == "~/cache:/x: the host folder is on a network or automounted volume"
    assert recorder.calls == []


def test_resolvers_share_one_worker_budget(tmp_path: Path) -> None:
    release = threading.Event()

    def stuck(path: str) -> str:
        release.wait(5)
        return path

    try:
        for index in range(RESOLVE_WORKERS):
            local_resolver((PurePosixPath(tmp_path),), timeout=0.01, follow=stuck)(
                PurePosixPath(tmp_path / str(index))
            )
        fresh = local_resolver((PurePosixPath(tmp_path),), follow=lambda path: path)
        assert fresh(PurePosixPath(tmp_path / "x")) == PurePosixPath("/")
    finally:
        release.set()


def test_an_automount_root_in_another_case_is_refused() -> None:
    recorder = Recorder()
    problem = container_mount_problem("/NET/host/x:/x", (VALIDATION_HOME,), recorder)
    assert problem == "/NET/host/x:/x: the host folder is on a network or automounted volume"
    assert recorder.calls == []
