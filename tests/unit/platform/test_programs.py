"""Finding a program only the user or root can change, outside what a run may write."""

import os
import stat
from pathlib import Path

import pytest

from code_factory.platform.programs import (
    REPOSITORY_VARIABLES,
    _holds_safely,
    absolute_path,
    child_environment,
    find_program,
    pinned_node,
    trusted_program,
    writers_known_as,
)

USER = 501


@pytest.mark.parametrize(
    ("owner", "mode", "expected"),
    [
        (USER, 0o755, True),  # the user's own
        (0, 0o755, True),  # root's, nobody else may write
        (USER, 0o775, True),  # the user's, and the user's group (Homebrew's admin group)
        (0, 0o775, False),  # root's but its group may write: who is in it is not known
        (USER, 0o757, False),  # others may write
        (USER, 0o777, False),
        (0, 0o757, False),
        (502, 0o755, False),  # another user's
        (502, 0o700, False),
    ],
)
def test_writers_are_known_when_only_root_or_the_user_can_change_it(
    owner: int, mode: int, *, expected: bool
) -> None:
    assert writers_known_as(owner, mode, USER) is expected


def make_program(folder: Path, name: str = "tool", mode: int = 0o755) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o755)
    program = folder / name
    program.write_text("#!/bin/sh\n")
    program.chmod(mode)
    return program.resolve()


def test_a_program_in_a_trusted_absolute_folder_is_found_as_its_real_file(tmp_path: Path) -> None:
    program = make_program(tmp_path / "bin")
    assert trusted_program("tool", [], search_path=str(tmp_path / "bin")) == program


def test_the_first_trusted_folder_of_the_path_wins_and_an_untrusted_one_is_skipped(
    tmp_path: Path,
) -> None:
    make_program(tmp_path / "open")
    (tmp_path / "open").chmod(0o777)
    later = make_program(tmp_path / "later")
    search = f"{tmp_path / 'open'}:{tmp_path / 'later'}"
    assert trusted_program("tool", [], search_path=search) == later


def test_a_folder_others_can_write_is_not_trusted(tmp_path: Path) -> None:
    make_program(tmp_path / "bin")
    (tmp_path / "bin").chmod(0o777)
    assert trusted_program("tool", [], search_path=str(tmp_path / "bin")) is None


def test_a_program_others_can_write_is_not_trusted(tmp_path: Path) -> None:
    make_program(tmp_path / "bin", mode=0o757)
    assert trusted_program("tool", [], search_path=str(tmp_path / "bin")) is None


def test_a_folder_a_run_may_write_is_not_trusted_even_when_it_is_the_users_own(
    tmp_path: Path,
) -> None:
    make_program(tmp_path / "clone" / "bin")
    search = str(tmp_path / "clone" / "bin")
    assert trusted_program("tool", [tmp_path / "clone"], search_path=search) is None
    assert trusted_program("tool", [tmp_path / "elsewhere"], search_path=search) is not None


def test_a_relative_folder_of_the_path_is_never_searched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_program(tmp_path / "bin")
    monkeypatch.chdir(tmp_path)
    assert trusted_program("tool", [], search_path="bin") is None


def test_a_file_without_an_execute_bit_is_not_a_program(tmp_path: Path) -> None:
    make_program(tmp_path / "bin", mode=0o644)
    assert trusted_program("tool", [], search_path=str(tmp_path / "bin")) is None


def test_a_link_in_a_trusted_folder_resolves_to_its_target(tmp_path: Path) -> None:
    real = make_program(tmp_path / "real")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin").chmod(0o755)
    (tmp_path / "bin" / "tool").symlink_to(real)
    assert trusted_program("tool", [], search_path=str(tmp_path / "bin")) == real


def test_a_link_in_a_folder_others_can_write_is_refused(tmp_path: Path) -> None:
    real = make_program(tmp_path / "real")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "tool").symlink_to(real)
    (tmp_path / "bin").chmod(0o777)
    assert trusted_program("tool", [], search_path=str(tmp_path / "bin")) is None


def test_a_loop_of_links_is_refused_instead_of_followed_forever(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin").chmod(0o755)
    (tmp_path / "bin" / "tool").symlink_to(tmp_path / "bin" / "other")
    (tmp_path / "bin" / "other").symlink_to(tmp_path / "bin" / "tool")
    assert trusted_program("tool", [], search_path=str(tmp_path / "bin")) is None


def test_a_chain_of_thirty_two_links_is_followed_and_thirty_three_is_not(tmp_path: Path) -> None:
    real = make_program(tmp_path / "real")
    folder = tmp_path / "bin"
    folder.mkdir()
    folder.chmod(0o755)
    previous = real
    for index in range(33):
        link = folder / f"l{index}"
        link.symlink_to(previous)
        previous = link
        if index == 31:  # the 32nd link
            assert trusted_program(link.name, [], search_path=str(folder)) == real
    assert trusted_program("l32", [], search_path=str(folder)) is None


def test_an_absolute_name_is_taken_as_it_is_when_the_system_would_start_it(
    tmp_path: Path,
) -> None:
    program = make_program(tmp_path / "bin")
    assert trusted_program(str(program), [], search_path="") == program
    assert trusted_program(str(tmp_path / "bin" / "missing"), [], search_path="") is None


def test_the_absolute_path_keeps_trusted_absolute_folders_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "relative").mkdir()
    (tmp_path / "relative").chmod(0o755)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "open").mkdir()
    for name in ("a", "b"):
        (tmp_path / name).chmod(0o755)
    (tmp_path / "open").chmod(0o777)
    search = f"{tmp_path / 'b'}:relative:{tmp_path / 'open'}:{tmp_path / 'a'}:{tmp_path / 'gone'}"
    assert (
        absolute_path([], search_path=search)
        == f"{(tmp_path / 'b').resolve()}:{(tmp_path / 'a').resolve()}"
    )


def test_the_repository_variables_are_removed_from_a_child_environment() -> None:
    env = dict.fromkeys(REPOSITORY_VARIABLES, "x") | {"HOME": "/h", "LC_ALL": "C"}
    assert child_environment(env) == {"HOME": "/h", "LC_ALL": "C"}
    assert REPOSITORY_VARIABLES == (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_PREFIX",
    )


def node_home(tmp_path: Path, version: str) -> Path:
    bin_folder = tmp_path / "home" / ".nvm" / "versions" / "node" / f"v{version}" / "bin"
    bin_folder.mkdir(parents=True)
    for folder in (tmp_path / "home" / ".nvm" / "versions" / "node" / f"v{version}", bin_folder):
        folder.chmod(0o755)
    return bin_folder.resolve()


@pytest.mark.parametrize("text", ["v22.1.0\n", "22.1.0", "  v22.1.0  "])
def test_a_pinned_version_names_the_installed_nodes_bin_folder(tmp_path: Path, text: str) -> None:
    folder = node_home(tmp_path, "22.1.0")
    assert pinned_node(text, [], home=tmp_path / "home") == folder


@pytest.mark.parametrize(
    "text",
    ["", "lts/*", "../22", "v22..1", "v22.1.x", "v22.1.0 # x", None],
)
def test_text_that_is_not_a_plain_version_pins_nothing(tmp_path: Path, text: str | None) -> None:
    node_home(tmp_path, "22.1.0")
    assert pinned_node(text, [], home=tmp_path / "home") is None


def test_a_pinned_node_that_is_not_installed_or_not_trusted_pins_nothing(tmp_path: Path) -> None:
    assert pinned_node("v20.0.0", [], home=tmp_path / "home") is None
    folder = node_home(tmp_path, "22.1.0")
    folder.chmod(0o777)
    assert pinned_node("v22.1.0", [], home=tmp_path / "home") is None
    folder.chmod(stat.S_IRWXU)
    assert pinned_node("v22.1.0", [], home=tmp_path / "home") == folder


async def test_find_program_runs_the_walk_off_the_loop_and_prefers_the_pinned_folder(
    tmp_path: Path,
) -> None:
    pinned = make_program(tmp_path / "pinned").parent
    make_program(tmp_path / "bin")
    found = await find_program("tool", [], search_path=str(tmp_path / "bin"), pinned=pinned)
    assert found == pinned / "tool"
    assert (
        await find_program("tool", [], search_path=str(tmp_path / "bin"))
        == (tmp_path / "bin" / "tool").resolve()
    )
    assert await find_program("nothing", [], search_path=str(tmp_path / "bin")) is None


def test_a_nvmrc_of_thirty_two_bytes_is_read_and_one_of_thirty_three_is_not(
    tmp_path: Path,
) -> None:
    fits = ".".join(["1"] * 16)  # 31 characters, 32 with the leading v
    too_long = ".".join(["1"] * 17)  # 33 characters
    folder = node_home(tmp_path, fits)
    node_home(tmp_path, too_long)
    assert pinned_node(f"v{fits}", [], home=tmp_path / "home") == folder
    assert pinned_node(too_long, [], home=tmp_path / "home") is None


def test_a_folder_whose_parent_others_can_rename_is_not_trusted(tmp_path: Path) -> None:
    make_program(tmp_path / "open" / "bin")
    (tmp_path / "open").chmod(0o777)
    assert trusted_program("tool", [], search_path=str(tmp_path / "open" / "bin")) is None


def test_a_link_to_a_file_in_a_folder_others_can_write_is_not_trusted(tmp_path: Path) -> None:
    real = make_program(tmp_path / "open")
    (tmp_path / "open").chmod(0o777)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin").chmod(0o755)
    (tmp_path / "bin" / "tool").symlink_to(real)
    assert trusted_program("tool", [], search_path=str(tmp_path / "bin")) is None


def test_a_link_to_a_folder_whose_real_parent_others_can_rename_is_not_trusted(
    tmp_path: Path,
) -> None:
    make_program(tmp_path / "open" / "bin")
    (tmp_path / "open").chmod(0o777)
    (tmp_path / "links").mkdir()
    (tmp_path / "links").chmod(0o755)
    (tmp_path / "links" / "b").symlink_to(tmp_path / "open" / "bin")
    search = str(tmp_path / "links" / "b")
    assert trusted_program("tool", [], search_path=search) is None
    assert absolute_path([], search_path=search) == ""


def test_a_place_written_through_a_link_still_excludes_what_is_under_it(tmp_path: Path) -> None:
    make_program(tmp_path / "clone" / "bin")
    (tmp_path / "alias").symlink_to(tmp_path / "clone")
    search = str(tmp_path / "clone" / "bin")
    assert trusted_program("tool", [tmp_path / "alias"], search_path=search) is None


def test_a_link_sitting_inside_a_place_a_run_may_write_is_refused(tmp_path: Path) -> None:
    make_program(tmp_path / "safe" / "bin")
    (tmp_path / "clone").mkdir()
    (tmp_path / "clone").chmod(0o755)
    (tmp_path / "clone" / "link").symlink_to(tmp_path / "safe" / "bin")
    search = str(tmp_path / "clone" / "link")
    assert trusted_program("tool", [tmp_path / "clone"], search_path=search) is None


def test_the_same_link_outside_every_place_is_followed(tmp_path: Path) -> None:
    real = make_program(tmp_path / "safe" / "bin")
    (tmp_path / "clone").mkdir()
    (tmp_path / "clone").chmod(0o755)
    (tmp_path / "clone" / "link").symlink_to(tmp_path / "safe" / "bin")
    assert trusted_program("tool", [], search_path=str(tmp_path / "clone" / "link")) == real


def stat_of(uid: int, mode: int) -> os.stat_result:
    return os.stat_result((stat.S_IFDIR | mode, 1, 1, 2, uid, 0, 0, 0, 0, 0))


@pytest.mark.parametrize(
    ("uid", "expected"),
    [(0, True), (os.getuid(), True), (os.getuid() + 1, False)],
)
def test_a_sticky_folder_others_can_write_holds_safely_only_for_root_or_the_user(
    monkeypatch: pytest.MonkeyPatch, uid: int, *, expected: bool
) -> None:
    monkeypatch.setattr(Path, "stat", lambda _self, **_kw: stat_of(uid, 0o1777))
    assert _holds_safely(Path("/tmp")) is expected  # noqa: S108  # never read: stat is replaced


def test_digits_outside_ascii_pin_nothing(tmp_path: Path) -> None:
    folder = tmp_path / "home" / ".nvm" / "versions" / "node" / "v\uff12\uff12" / "bin"
    folder.mkdir(parents=True)
    for part in (folder.parent, folder):
        part.chmod(0o755)
    assert pinned_node("\uff12\uff12", [], home=tmp_path / "home") is None
