"""Link resolution of mount paths: a walk that never probes an automount root, and a scan that
runs out of time says so instead of passing or dropping the config."""

import os
from pathlib import Path, PurePosixPath

import pytest

from code_factory.settings.adapters import local_resolver
from code_factory.settings.adapters.resolver import AutomountReached, walk_realpath
from code_factory.settings.rules.secrets import Unjudged


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


def test_a_walk_cannot_step_up_from_a_missing_name(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        walk_realpath(str(tmp_path / "missing" / ".." / "x"))


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


@pytest.mark.parametrize("target", ["file/.", "file/", "file//"])
def test_a_link_to_a_file_with_a_directory_suffix_is_an_error(tmp_path: Path, target: str) -> None:
    (tmp_path / "file").write_text("x")
    (tmp_path / "link").symlink_to(target)
    with pytest.raises(NotADirectoryError):
        walk_realpath(str(tmp_path / "link"))
    with pytest.raises(NotADirectoryError):
        os.path.realpath(tmp_path / "link", strict=True)


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
