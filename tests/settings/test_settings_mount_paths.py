"""A checks container mount is judged by the folder it reaches on disk, not by its spelling: a
doubled slash, a link or another case of a secret folder is refused, an unrelated folder is not."""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.settings.adapters import RESOLVE_WORKERS, local_resolver
from code_factory.settings.adapters import resolver as resolver_module
from code_factory.settings.rules import config as config_rules
from code_factory.settings.rules.secrets import (
    VALIDATION_HOME,
    container_mount_problem,
    mount_reaches_secrets,
)
from code_factory.settings.service import SettingsService
from settings_support import write

CONFIG = ".code-factory/config.toml"
REACHES = "the host folder is, holds or is in the home folder or a secret folder"


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


@pytest.fixture
def service(uow: UnitOfWork, home: Path) -> SettingsService:
    return SettingsService(uow, clock=lambda: datetime(2026, 11, 2, tzinfo=UTC), home=home)


async def problems(service: SettingsService, tmp_path: Path, mount: str) -> list[str]:
    repo = tmp_path / "repo"
    write(repo, CONFIG, f'[checks]\ncommand = "x"\ncontainer_mounts = ["{mount}:/x"]\n')
    return [str(p) for p in (await service.check_config(repo)).problems]


async def test_a_doubled_leading_slash_does_not_hide_a_secret(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    found = await problems(service, tmp_path, f"/{home}/.ssh")
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_link_into_a_secret_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    link = tmp_path / "repo" / "innocent"
    link.parent.mkdir()
    link.symlink_to(home / ".ssh")
    found = await problems(service, tmp_path, str(link))
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_link_to_the_home_folder_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    link = tmp_path / "repo" / "shortcut"
    link.parent.mkdir()
    link.symlink_to(home)
    found = await problems(service, tmp_path, str(link))
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_path_through_a_parent_step_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    found = await problems(service, tmp_path, f"{home}/work/../.ssh")
    assert len(found) == 1


async def test_a_path_in_another_case_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    found = await problems(service, tmp_path, str(home / ".SSH"))
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_folder_outside_the_secrets_is_accepted_directly_and_through_a_link(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    link = tmp_path / "repo" / "cache-link"
    link.parent.mkdir()
    link.symlink_to(cache)
    assert await problems(service, tmp_path, str(cache)) == []
    assert await problems(service, tmp_path, str(link)) == []
    assert await problems(service, tmp_path, str(home / "work")) == []


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


async def test_a_link_retargeted_after_a_load_is_judged_again(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    repo = tmp_path / "repo"
    link = repo / "cache"
    link.parent.mkdir()
    link.symlink_to(home / "work")
    write(
        repo,
        CONFIG,
        '[checks]\ncommand = "x"\ncontainer_mounts = ["cache:/x"]\n'.replace("cache", str(link)),
    )
    first = await service.load(repo)
    assert first.checks is not None
    assert first.checks.container_mounts == [f"{link}:/x"]
    link.unlink()
    link.symlink_to(home / ".ssh")
    second = await service.load(repo)
    assert second.checks is not None
    assert second.checks.container_mounts is None


async def test_a_link_loop_is_refused(service: SettingsService, tmp_path: Path) -> None:
    loop = tmp_path / "repo" / "loop"
    loop.parent.mkdir()
    loop.symlink_to(loop)
    found = await problems(service, tmp_path, str(loop))
    assert [p.endswith(REACHES) for p in found] == [True]


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


async def test_a_key_spelled_with_an_escape_is_still_judged_again_on_every_load(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    repo = tmp_path / "repo"
    link = repo / "cache"
    link.parent.mkdir()
    link.symlink_to(home / "work")
    write(
        repo,
        CONFIG,
        f'[checks]\ncommand = "x"\n"container\\u005fmounts" = ["{link}:/x"]\n',
    )
    first = await service.load(repo)
    assert first.checks is not None
    assert first.checks.container_mounts == [f"{link}:/x"]
    link.unlink()
    link.symlink_to(home / ".ssh")
    second = await service.load(repo)
    assert second.checks is not None
    assert second.checks.container_mounts is None


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


async def test_a_check_resolves_the_mounts_once(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[object] = []

    def counting(roots):  # noqa: ANN001, ANN202
        built.append(roots)
        return lambda path: path

    monkeypatch.setattr("code_factory.settings.service.checks.local_resolver", counting)
    await problems(service, tmp_path, str(tmp_path / "repo" / "cache"))
    assert len(built) == 1


async def test_a_directory_holding_a_linked_secret_file_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "config.json").write_text("{}")
    (home / ".docker").mkdir()
    (home / ".docker" / "config.json").symlink_to(dotfiles / "config.json")
    found = await problems(service, tmp_path, str(home / ".docker"))
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_load_parses_the_config_off_the_event_loop(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop_thread = threading.get_ident()
    parsers: list[int] = []
    real = config_rules.parse_toml

    def recording(text: str):  # noqa: ANN202
        parsers.append(threading.get_ident())
        return real(text)

    monkeypatch.setattr(config_rules, "parse_toml", recording)
    repo = tmp_path / "repo"
    write(repo, CONFIG, '[checks]\ncommand = "x"\ncontainer_mounts = ["/srv/a:/x"]\n')
    await service.load(repo)
    assert parsers
    assert loop_thread not in parsers
