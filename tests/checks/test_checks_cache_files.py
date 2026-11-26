"""The build cache and the logs folder with real folders and real links in `tmp_path`.

Every case that names a link plants one where a commit under check could: the folder or file
behind it must stay untouched.
"""

from pathlib import Path

import pytest

from code_factory.checks.adapters import LogFiles, cache


def make(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_forget_removes_a_tickets_cache_and_a_missing_one_is_no_error(tmp_path: Path) -> None:
    make(tmp_path / "check-cache" / "CF-1" / "linux-target" / "artifact")
    cache.forget(tmp_path, "CF-1")
    assert not (tmp_path / "check-cache" / "CF-1").exists()
    cache.forget(tmp_path, "CF-1")  # none left: no error


def test_an_id_that_looks_like_a_path_removes_nothing_outside_its_own_folder(
    tmp_path: Path,
) -> None:
    keep = make(tmp_path / "keep" / "file")
    make(tmp_path / "check-cache" / "______keep" / "file")
    cache.forget(tmp_path, "../../keep")
    assert keep.exists()
    assert not (tmp_path / "check-cache" / "______keep").exists()


def test_an_empty_ticket_id_has_no_cache_to_forget(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"^a ticket's cache has a name$"):
        cache.forget(tmp_path, "")


def test_a_cache_folder_that_is_a_link_is_never_followed_or_removed(tmp_path: Path) -> None:
    outside = make(tmp_path / "outside" / "precious")
    (tmp_path / "check-cache").mkdir()
    (tmp_path / "check-cache" / "CF-1").symlink_to(outside.parent)
    cache.forget(tmp_path, "CF-1")
    assert outside.exists()
    assert (tmp_path / "check-cache" / "CF-1").is_symlink()


def test_a_check_cache_folder_that_is_a_link_is_never_followed(tmp_path: Path) -> None:
    outside = make(tmp_path / "outside" / "CF-1" / "precious")
    (tmp_path / "check-cache").symlink_to(outside.parent.parent)
    cache.forget(tmp_path, "CF-1")
    assert outside.exists()
    assert cache.folders(tmp_path) == []


def test_the_caches_listed_are_real_folders_named_as_the_key_names_them(tmp_path: Path) -> None:
    make(tmp_path / "check-cache" / "CF-2" / "a")
    make(tmp_path / "check-cache" / "CF-1" / "a")
    make(tmp_path / "check-cache" / "a file")
    make(tmp_path / "check-cache" / "has space" / "a")
    (tmp_path / "check-cache" / "CF-3").symlink_to(tmp_path)
    assert [name for name, _ in cache.folders(tmp_path)] == ["CF-1", "CF-2"]


def test_a_cache_is_handed_to_a_snapshot_moved_not_copied(tmp_path: Path) -> None:
    state, tree = tmp_path / "state", tmp_path / "tree"
    make(state / "check-cache" / "CF-1" / "linux-target" / "artifact", "built")
    tree.mkdir()
    place = tree / cache.LINUX_TARGET
    cache.adopt(state, "CF-1", "linux-target", tree, place)
    assert (place / "artifact").read_text() == "built"
    assert not (state / "check-cache" / "CF-1" / "linux-target").exists()


def test_a_cache_is_not_handed_into_a_link_in_the_tree(tmp_path: Path) -> None:
    state, tree = tmp_path / "state", tmp_path / "tree"
    make(state / "check-cache" / "CF-1" / "linux-target" / "artifact", "built")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    tree.mkdir()
    (tree / "target").symlink_to(elsewhere)
    cache.adopt(state, "CF-1", "linux-target", tree, tree / cache.LINUX_TARGET)
    assert list(elsewhere.iterdir()) == []
    assert (state / "check-cache" / "CF-1" / "linux-target" / "artifact").exists()


def test_a_passed_snapshot_gives_its_build_back_unless_another_filled_the_cache(
    tmp_path: Path,
) -> None:
    state, tree = tmp_path / "state", tmp_path / "tree"
    place = tree / cache.LINUX_TARGET
    make(place / "new", "new")
    cache.keep(state, "CF-1", "linux-target", tree, place)
    assert (state / "check-cache" / "CF-1" / "linux-target" / "new").read_text() == "new"
    assert not place.exists()

    make(place / "newer", "newer")
    cache.keep(state, "CF-1", "linux-target", tree, place)
    kept = state / "check-cache" / "CF-1" / "linux-target"
    assert (kept / "new").exists()
    assert not (kept / "newer").exists()
    assert not place.exists()


def test_a_build_folder_that_is_a_link_is_neither_kept_nor_removed(tmp_path: Path) -> None:
    state, tree = tmp_path / "state", tmp_path / "tree"
    outside = make(tmp_path / "outside" / "precious")
    (tree / "target").mkdir(parents=True)
    (tree / "target" / "linux").symlink_to(outside.parent)
    cache.keep(state, "CF-1", "linux-target", tree, tree / cache.LINUX_TARGET)
    cache.discard(tree, tree / cache.LINUX_TARGET)
    assert outside.exists()
    assert not (state / "check-cache" / "CF-1" / "linux-target").exists()


def test_real_folders_refuses_a_link_and_a_path_outside_the_base(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").symlink_to(tmp_path / "a")
    assert cache.real_folders(tmp_path, tmp_path / "a" / "missing" / "deeper")
    assert not cache.real_folders(tmp_path, tmp_path / "b" / "x")
    assert not cache.real_folders(tmp_path / "a", tmp_path / "b")


async def test_a_log_of_the_ticket_in_the_logs_folder_may_be_opened(tmp_path: Path) -> None:
    logs = LogFiles(tmp_path)
    own = make(logs.folder / "sample-CF-1-17.log", "hello")
    assert await logs.within("sample", "CF-1", str(own)) == own.resolve()


@pytest.mark.parametrize(
    "name",
    ["sample-CF-2-17.log", "other-CF-1-17.log", "sample-CF-1-17.txt", "sample-CF-1-x.log"],
)
async def test_another_tickets_or_repositorys_log_and_other_names_may_not(
    tmp_path: Path, name: str
) -> None:
    logs = LogFiles(tmp_path)
    other = make(logs.folder / name)
    assert await logs.within("sample", "CF-1", str(other)) is None


async def test_a_log_reached_by_a_link_or_outside_the_folder_or_not_a_file_may_not(
    tmp_path: Path,
) -> None:
    logs = LogFiles(tmp_path)
    logs.folder.mkdir(parents=True)
    secret = make(tmp_path / "secret.txt", "secret")
    (logs.folder / "sample-CF-1-1.log").symlink_to(secret)
    assert await logs.within("sample", "CF-1", str(logs.folder / "sample-CF-1-1.log")) is None
    outside = make(tmp_path / "sample-CF-1-2.log")
    assert await logs.within("sample", "CF-1", str(outside)) is None
    (logs.folder / "sample-CF-1-3.log").mkdir()
    assert await logs.within("sample", "CF-1", str(logs.folder / "sample-CF-1-3.log")) is None
    assert await logs.within("sample", "CF-1", str(tmp_path / "missing.log")) is None


async def test_a_log_is_paged_by_byte_offset(tmp_path: Path) -> None:
    logs = LogFiles(tmp_path)
    path = make(logs.folder / "sample-CF-1-1.log", "0123456789")
    assert await logs.page(path, 0, 4) == ("0123", 10, 4)
    assert await logs.page(path, 4, 4) == ("4567", 10, 8)
    assert await logs.page(path, 8, 4) == ("89", 10, 10)
    assert await logs.page(path, 50, 4) == ("", 10, 10)
