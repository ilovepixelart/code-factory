"""Link resolution of mount paths: a walk that never probes an automount root, and a scan that
runs out of time says so instead of passing or dropping the config."""

import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.settings import service as service_module
from code_factory.settings.adapters import Files, in_thread, local_resolver
from code_factory.settings.adapters import files as files_module
from code_factory.settings.adapters.resolver import AutomountReached, walk_realpath
from code_factory.settings.models.errors import ConfigUnjudgedError
from code_factory.settings.rules.secrets import Unjudged
from code_factory.settings.service import SettingsService
from settings_support import write

CONFIG = ".code-factory/config.toml"
REACHES = "the host folder is, holds or is in the home folder or a secret folder"


class Probe:
    """`lstat` and `readlink` that record every path they are asked about."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    def lstat(self, path: str) -> os.stat_result:
        self.paths.append(path)
        return os.lstat(path)

    def readlink(self, path: str) -> str:
        self.paths.append(path)
        return str(Path(path).readlink())


def test_a_link_into_an_automount_root_is_refused_before_the_root_is_probed(
    tmp_path: Path,
) -> None:
    (tmp_path / "link").symlink_to("/net/host/x")
    (tmp_path / "relative").symlink_to("link")
    probe = Probe()
    for name in ("link", "relative"):
        with pytest.raises(AutomountReached):
            walk_realpath(str(tmp_path / name), probe.lstat, probe.readlink)
    assert probe.paths
    assert [p for p in probe.paths if p.casefold().startswith("/net")] == []


def build_tree(base: Path) -> None:
    (base / "real" / "sub").mkdir(parents=True)
    (base / "abs").symlink_to(base / "real")
    (base / "rel").symlink_to("real/sub")
    (base / "up").symlink_to("real/sub/..")
    (base / "chain").symlink_to("abs")


@pytest.mark.parametrize(
    "tail",
    ["real", "abs", "rel", "up/sub", "chain/sub", "abs/missing/deeper", "real/../abs/sub", "gone"],
)
def test_the_walk_resolves_like_realpath(tmp_path: Path, tail: str) -> None:
    build_tree(tmp_path)
    path = str(tmp_path / tail)
    assert walk_realpath(path) == os.path.realpath(path, strict=os.path.ALLOW_MISSING)


def test_a_link_loop_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "loop").symlink_to(tmp_path / "loop")
    with pytest.raises(OSError, match=r"Too many levels"):
        walk_realpath(str(tmp_path / "loop"))


def test_a_file_is_not_taken_for_a_link_and_nothing_resolves_below_it(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x")
    assert walk_realpath(str(tmp_path / "f")) == os.path.realpath(tmp_path / "f")
    with pytest.raises(NotADirectoryError):
        walk_realpath(str(tmp_path / "f" / "below"))


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_same_path_is_resolved_once_per_scan(tmp_path: Path) -> None:
    asked: list[str] = []

    def follow(path: str) -> str:
        asked.append(path)
        return path

    resolve = local_resolver((PurePosixPath(tmp_path),), follow=follow)
    inside = PurePosixPath(tmp_path / "home")
    assert resolve(inside) == resolve(inside) == inside
    assert asked == [str(inside)]


def test_a_scan_past_its_deadline_cannot_judge_anything_more(tmp_path: Path) -> None:
    clock = Clock()
    resolve = local_resolver(
        (PurePosixPath(tmp_path),), deadline_s=5.0, clock=clock, follow=lambda path: path
    )
    inside = PurePosixPath(tmp_path / "a")
    assert resolve(inside) == inside
    clock.now = 5.0
    with pytest.raises(Unjudged):
        resolve(PurePosixPath(tmp_path / "b"))


def test_a_lookup_that_finishes_after_the_deadline_is_not_judged(tmp_path: Path) -> None:
    clock = Clock()

    def slow(path: str) -> str:
        clock.now = 5.0
        return path

    resolve = local_resolver((PurePosixPath(tmp_path),), deadline_s=5.0, clock=clock, follow=slow)
    with pytest.raises(Unjudged):
        resolve(PurePosixPath(tmp_path / "a"))


def test_a_lookup_that_finishes_just_before_the_deadline_is_judged(tmp_path: Path) -> None:
    clock = Clock()

    def quick(path: str) -> str:
        clock.now = 4.9
        return path

    resolve = local_resolver((PurePosixPath(tmp_path),), deadline_s=5.0, clock=clock, follow=quick)
    inside = PurePosixPath(tmp_path / "a")
    assert resolve(inside) == inside


@pytest.fixture
def home(tmp_path: Path) -> Path:
    found = tmp_path / "home" / "alex"
    (found / ".ssh").mkdir(parents=True)
    return found


@pytest.fixture
def service(uow: UnitOfWork, home: Path) -> SettingsService:
    return SettingsService(uow, clock=lambda: datetime(2026, 11, 2, tzinfo=UTC), home=home)


def write_mounts(tmp_path: Path, mounts: list[str]) -> Path:
    repo = tmp_path / "repo"
    items = ", ".join(f'"{m}:/x"' for m in mounts)
    write(repo, CONFIG, f'[checks]\ncommand = "x"\ncontainer_mounts = [{items}]\n')
    return repo


async def test_a_repository_link_into_an_automount_root_is_refused(
    service: SettingsService, tmp_path: Path
) -> None:
    repo = write_mounts(tmp_path, [str(tmp_path / "repo" / "share")])
    (repo / "share").symlink_to("/net/host/x")
    report = await service.check_config(repo)
    assert [p.endswith(REACHES) for p in map(str, report.problems)] == [True]


def instant_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    real = local_resolver
    monkeypatch.setattr(
        "code_factory.settings.service.checks.local_resolver",
        lambda roots: real(roots, deadline_s=0.0),
    )


async def test_a_check_that_runs_out_of_time_names_the_config_and_the_mounts(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_mounts(tmp_path, ["/srv/a", "/srv/b"])
    instant_deadline(monkeypatch)
    report = await service.check_config(repo)
    expected = (
        f"{CONFIG}:0: could not judge container_mounts /srv/a:/x, /srv/b:/x in time; "
        "no run starts with this config until they can be judged"
    )
    assert [str(p) for p in report.problems] == [expected]


async def test_a_load_that_runs_out_of_time_refuses_and_is_not_remembered(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_mounts(tmp_path, ["/srv/a"])
    with monkeypatch.context() as patch:
        instant_deadline(patch)
        with pytest.raises(ConfigUnjudgedError) as raised:
            await service.load(repo)
    expected = (
        f"{CONFIG}: could not judge container_mounts /srv/a:/x in time; "
        "no run starts with this config until they can be judged"
    )
    assert str(raised.value) == expected
    loaded = await service.load(repo)
    assert loaded.checks is not None
    assert loaded.checks.container_mounts == ["/srv/a:/x"]


async def test_a_parent_step_after_a_missing_name_cannot_hide_a_link_to_a_secret(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    (home / "shortcut").symlink_to(home / ".ssh")
    (home / "hop").symlink_to("nonexistent/../shortcut")
    repo = write_mounts(tmp_path, [f"{home}/hop"])
    report = await service.check_config(repo)
    assert [p.endswith(REACHES) for p in map(str, report.problems)] == [True]


def test_a_walk_cannot_step_up_from_a_missing_name(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        walk_realpath(str(tmp_path / "missing" / ".." / "x"))


async def test_a_missing_name_without_a_parent_step_is_allowed(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    repo = write_mounts(tmp_path, [f"{home}/missing/file"])
    assert (await service.check_config(repo)).problems == ()


def test_a_parent_step_after_a_file_is_not_a_directory_error(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x")
    (tmp_path / "hop").symlink_to("f/..")
    with pytest.raises(NotADirectoryError):
        walk_realpath(str(tmp_path / "hop"))
    with pytest.raises(NotADirectoryError):
        os.path.realpath(tmp_path / "hop", strict=os.path.ALLOW_MISSING)


def test_a_name_too_long_below_a_missing_one_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="File name too long"):
        walk_realpath(str(tmp_path / "missing" / ("a" * 5000)))


def first_calls_time_out(real: Callable[..., Any], times: int) -> Callable[..., Any]:
    """`in_thread` whose first `times` calls report their own timeout."""
    calls: list[object] = []

    async def wrapper(function: Callable[..., Any], *args: object) -> Any:  # noqa: ANN401
        calls.append(function)
        return None if len(calls) <= times else await real(function, *args)

    return wrapper


async def test_a_timed_out_read_of_a_config_with_mounts_refuses_and_is_not_remembered(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = write_mounts(tmp_path, ["/srv/a"])
    with monkeypatch.context() as patch:
        patch.setattr(service_module, "in_thread", first_calls_time_out(in_thread, 1))
        with pytest.raises(ConfigUnjudgedError) as raised:
            await service.load(repo)
    assert str(raised.value) == (
        f"{CONFIG}: could not judge container_mounts in time; "
        "no run starts with this config until they can be judged"
    )
    loaded = await service.load(repo)
    assert loaded.checks is not None
    assert loaded.checks.container_mounts == ["/srv/a:/x"]


async def test_a_timed_out_read_of_a_config_without_mounts_is_still_empty(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, CONFIG, '[tickets]\nprefix = "ABC"\n')
    monkeypatch.setattr(service_module, "in_thread", first_calls_time_out(in_thread, 1))
    assert await service.ticket_prefix(tmp_path) == "CF"


async def test_a_config_whose_mounts_cannot_be_looked_for_in_time_refuses(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, CONFIG, '[tickets]\nprefix = "ABC"\n')
    monkeypatch.setattr(service_module, "in_thread", first_calls_time_out(in_thread, 2))
    with pytest.raises(ConfigUnjudgedError):
        await service.load(tmp_path)


@pytest.mark.parametrize("target", ["file/.", "file/", "file//"])
def test_a_link_to_a_file_with_a_directory_suffix_is_an_error(tmp_path: Path, target: str) -> None:
    (tmp_path / "file").write_text("x")
    (tmp_path / "link").symlink_to(target)
    with pytest.raises(NotADirectoryError):
        walk_realpath(str(tmp_path / "link"))
    with pytest.raises(NotADirectoryError):
        os.path.realpath(tmp_path / "link", strict=True)


async def test_a_scan_never_asks_the_disk_about_the_synthetic_home(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/home` can be an automount map: only the real home and the repository are walked."""
    probe = Probe()
    monkeypatch.setattr(walk_realpath, "__defaults__", (probe.lstat, probe.readlink))
    repo = write_mounts(tmp_path, ["/srv/a"])
    assert (await service.check_config(repo)).problems == ()
    assert probe.paths
    assert [p for p in probe.paths if p == "/home" or p.startswith("/home/")] == []


def test_a_result_memoised_before_the_deadline_is_not_used_after_it(tmp_path: Path) -> None:
    clock = Clock()
    resolve = local_resolver(
        (PurePosixPath(tmp_path),), deadline_s=5.0, clock=clock, follow=lambda path: path
    )
    inside = PurePosixPath(tmp_path / "a")
    assert resolve(inside) == inside
    clock.now = 5.0
    with pytest.raises(Unjudged):
        resolve(inside)


def stalls_first_call(monkeypatch: pytest.MonkeyPatch, name: str) -> threading.Event:
    """The file helper `name` blocks on the returned event on its first call only."""
    real = getattr(files_module, name)
    release = threading.Event()
    calls: list[object] = []

    def stalled(*args: Any) -> Any:  # noqa: ANN401
        calls.append(args)
        if len(calls) == 1:
            release.wait(10)
        return real(*args)

    monkeypatch.setattr(files_module, name, stalled)
    return release


@pytest.mark.parametrize("helper", ["_stat", "_read"])
async def test_a_file_call_that_times_out_refuses_the_config_and_is_not_remembered(
    uow: UnitOfWork, tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch, helper: str
) -> None:
    service = SettingsService(uow, files=Files(timeout=1.0), home=home)
    repo = write_mounts(tmp_path, ["/srv/a"])
    release = stalls_first_call(monkeypatch, helper)
    try:
        with pytest.raises(ConfigUnjudgedError) as raised:
            await service.load(repo)
    finally:
        release.set()
    assert str(raised.value) == (
        f"{CONFIG}: could not judge container_mounts in time; "
        "no run starts with this config until they can be judged"
    )
    loaded = await service.load(repo)
    assert loaded.checks is not None
    assert loaded.checks.container_mounts == ["/srv/a:/x"]


async def test_a_repository_without_a_config_still_reads_as_empty_after_a_timed_out_neighbour(
    uow: UnitOfWork, tmp_path: Path, home: Path
) -> None:
    service = SettingsService(uow, files=Files(timeout=0.1), home=home)
    assert await service.ticket_prefix(tmp_path) == "CF"


def test_a_link_into_the_synthetic_home_is_refused_before_it_is_probed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = Probe()
    monkeypatch.setattr(walk_realpath, "__defaults__", (probe.lstat, probe.readlink))
    (tmp_path / "link").symlink_to("/home/other/x")
    resolve = local_resolver((PurePosixPath(tmp_path),))
    assert resolve(PurePosixPath(tmp_path / "link")) == PurePosixPath("/")
    assert [p for p in probe.paths if p == "/home" or p.startswith("/home/")] == []


def test_a_link_into_a_local_root_below_home_is_still_followed(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    resolve = local_resolver((PurePosixPath(tmp_path),))
    assert resolve(PurePosixPath(tmp_path / "link")) == PurePosixPath(real.resolve())


async def test_a_scan_without_a_known_home_never_asks_the_disk_about_home(
    uow: UnitOfWork, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = SettingsService(uow, home=Path("/home"))
    probe = Probe()
    monkeypatch.setattr(walk_realpath, "__defaults__", (probe.lstat, probe.readlink))
    repo = write_mounts(tmp_path, ["/srv/a"])
    assert (await service.check_config(repo)).problems == ()
    assert [p for p in probe.paths if p == "/home" or p.startswith("/home/")] == []
