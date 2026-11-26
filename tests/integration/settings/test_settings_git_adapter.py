"""The git edge: a scrubbed environment, a timeout that reaps the child, a capped output, and the
base branch of an expiry check, against real repositories built in `tmp_path` (no network)."""

import os
from pathlib import Path

import pytest

from code_factory.settings.adapters import Fork, GitFacts
from settings_support import agit, arepository, write


def fake_git(tmp_path: Path, body: str) -> str:
    script = tmp_path / "fake-git"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    return str(script)


async def test_tracked_lists_only_files_git_tracks(tmp_path: Path) -> None:
    root = await arepository(
        tmp_path, {"deny.toml": "", "web/pnpm-workspace.yaml": "", "src/a.py": ""}
    )
    (root / "untracked").mkdir()
    (root / "untracked" / "deny.toml").write_text("")
    found = await GitFacts().tracked(root, ["**/deny.toml", "**/pnpm-workspace.yaml"])
    assert sorted(found) == ["deny.toml", "web/pnpm-workspace.yaml"]


async def test_tracked_is_empty_outside_a_repository(tmp_path: Path) -> None:
    assert await GitFacts().tracked(tmp_path, ["**/deny.toml"]) == []


async def test_a_hostile_git_environment_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = await arepository(tmp_path, {"deny.toml": ""})
    for name in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_PREFIX",
    ):
        monkeypatch.setenv(name, str(tmp_path / "nowhere"))
    assert await GitFacts().tracked(root, ["**/deny.toml"]) == ["deny.toml"]


async def test_grep_exists_looks_in_tracked_files_only(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {"tests/test_a.py": "async def test_flaky() -> None: ...\n"})
    facts = GitFacts()
    assert await facts.grep_exists(root, "def test_flaky(", ("tests/test_a.py",)) is True
    assert await facts.grep_exists(root, "def test_flaky(", ("*/test_a.py",)) is True
    assert await facts.grep_exists(root, "def test_other(", ("tests/test_a.py",)) is False
    assert await facts.grep_exists(root, "def test_flaky(", ("tests/test_b.py",)) is False


async def test_a_pattern_that_looks_like_an_option_is_searched_for_not_obeyed(
    tmp_path: Path,
) -> None:
    root = await arepository(tmp_path, {"a.txt": "--version\n"})
    facts = GitFacts()
    assert await facts.grep_exists(root, "--version", ("a.txt",)) is True
    assert await facts.grep_exists(root, "--no-such-text", ("a.txt",)) is False


async def test_a_git_that_hangs_times_out_and_is_reaped(tmp_path: Path) -> None:
    marker = tmp_path / "pid"
    executable = fake_git(tmp_path, f'echo $$ > "{marker}"\nexec sleep 30')
    facts = GitFacts(executable=executable, timeout=0.5, grace=0.5)
    assert await facts.tracked(tmp_path, ["**/deny.toml"]) == []
    pid = int(marker.read_text())
    assert pid > 1
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_output_past_the_cap_reads_as_a_failure_and_the_child_is_reaped(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "pid"
    executable = fake_git(tmp_path, f'echo $$ > "{marker}"\nhead -c 3000000 /dev/zero | tr "\\0" a')
    facts = GitFacts(executable=executable, output_limit=1024 * 1024)
    assert await facts.tracked(tmp_path, ["**/deny.toml"]) == []
    pid = int(marker.read_text())
    assert pid > 1
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_a_missing_git_reads_as_nothing_found(tmp_path: Path) -> None:
    facts = GitFacts(executable=str(tmp_path / "no-such-git"))
    assert await facts.tracked(tmp_path, ["**/deny.toml"]) == []
    assert await facts.grep_exists(tmp_path, "x", ("a",)) is False


async def commit(root: Path, message: str = "c") -> str:
    await agit(root, "commit", "-q", "-m", message)
    return await agit(root, "rev-parse", "HEAD")


async def test_a_branch_forks_from_main_and_lists_what_it_changed(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {"src/a.py": "a\n", "deny.toml": "d\n"})
    base = await commit(root)
    await agit(root, "checkout", "-q", "-b", "feature")
    (root / "deny.toml").write_text("d2\n")
    await agit(root, "add", "-A")
    head = await commit(root)
    fork = await GitFacts().fork(root, None)
    assert fork == Fork(base=base, head=head, changed=("deny.toml",))


async def test_main_itself_is_its_own_fork_point(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {"a": "a\n"})
    head = await commit(root)
    fork = await GitFacts().fork(root, None)
    assert (fork.base, fork.head) == (head, head)


async def test_master_is_the_base_when_there_is_no_main(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    await agit(root, "init", "-q", "-b", "master")
    (root / "a").write_text("a\n")
    await agit(root, "add", "-A")
    head = await commit(root)
    assert (await GitFacts().fork(root, None)).base == head


async def test_a_named_base_ref_is_used(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {"a": "a\n"})
    base = await commit(root)
    await agit(root, "checkout", "-q", "-b", "other")
    (root / "b").write_text("b\n")
    await agit(root, "add", "-A")
    await commit(root)
    fork = await GitFacts().fork(root, "main")
    assert fork.base == base
    assert fork.changed == ("b",)


async def test_no_commit_and_no_base_means_no_fork_point(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {"a": "a\n"})
    assert await GitFacts().fork(root, None) == Fork(base=None, head=None, changed=None)
    assert await GitFacts().fork(tmp_path, None) == Fork(base=None, head=None, changed=None)


async def test_a_base_ref_that_looks_like_an_option_is_no_base(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {"a": "a\n"})
    await commit(root)
    fork = await GitFacts().fork(root, "--output=/tmp/should-not-exist")
    assert fork.base is None


async def test_the_repository_root_is_found_from_a_folder_inside_it(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {"src/a.py": "a\n"})
    facts = GitFacts()
    assert await facts.toplevel(root / "src") == root.resolve()
    assert await facts.toplevel(tmp_path / "nowhere") is None


GUIDE = ".code-factory/REVIEW.md"


async def test_a_file_is_read_from_the_base_branch_not_the_working_tree(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {GUIDE: "on main\n"})
    await commit(root)
    await agit(root, "checkout", "-q", "-b", "feature")
    write(root, GUIDE, "on the branch\n")
    await agit(root, "commit", "-q", "-am", "edit")
    write(root, GUIDE, "uncommitted\n")
    assert await GitFacts().show_on_base(root, GUIDE) == ("main", "on main\n")


async def test_master_is_read_when_there_is_no_main(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    await agit(root, "init", "-q", "-b", "master")
    write(root, GUIDE, "on master\n")
    await agit(root, "add", "-A")
    await commit(root)
    assert await GitFacts().show_on_base(root, GUIDE) == ("master", "on master\n")


async def test_a_file_the_base_does_not_hold_is_none(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {"a": "a\n"})
    await commit(root)
    assert await GitFacts().show_on_base(root, GUIDE) is None


async def test_a_directory_or_a_repository_with_no_commit_is_none(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {"a": "a\n", "d/x": "x\n"})
    assert await GitFacts().show_on_base(root, GUIDE) is None
    await commit(root)
    assert await GitFacts().show_on_base(root, "d") is None


async def test_a_file_past_the_output_cap_is_none(tmp_path: Path) -> None:
    root = await arepository(tmp_path, {GUIDE: "x" * 2048})
    await commit(root)
    assert await GitFacts(output_limit=1024).show_on_base(root, GUIDE) is None
    assert await GitFacts(output_limit=4096).show_on_base(root, GUIDE) is not None


async def shadowed(tmp_path: Path) -> Path:
    """`main` commits the real guide; a second commit, off `main`, holds another one."""
    root = await arepository(tmp_path, {GUIDE: "real\n"})
    await commit(root)
    await agit(root, "checkout", "-q", "-b", "elsewhere")
    write(root, GUIDE, "shadow\n")
    await agit(root, "commit", "-q", "-am", "shadow")
    await agit(root, "checkout", "-q", "main")
    return root


async def test_a_tag_named_like_the_base_branch_does_not_replace_it(tmp_path: Path) -> None:
    root = await shadowed(tmp_path)
    await agit(root, "tag", "main", "elsewhere")
    assert await GitFacts().show_on_base(root, GUIDE) == ("main", "real\n")


async def test_a_branch_named_like_the_remote_head_does_not_replace_the_base_branch(
    tmp_path: Path,
) -> None:
    root = await shadowed(tmp_path)
    await agit(root, "branch", "origin/HEAD", "elsewhere")
    assert await GitFacts().show_on_base(root, GUIDE) == ("main", "real\n")


async def test_the_remote_head_is_the_base_when_it_exists(tmp_path: Path) -> None:
    root = await shadowed(tmp_path)
    await agit(root, "update-ref", "refs/remotes/origin/main", "elsewhere")
    await agit(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    assert await GitFacts().show_on_base(root, GUIDE) == ("origin/HEAD", "shadow\n")


async def test_a_tag_spelled_like_a_missing_branch_ref_does_not_stand_in_for_it(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    await agit(root, "init", "-q", "-b", "master")
    write(root, GUIDE, "real\n")
    await agit(root, "add", "-A")
    await commit(root)
    await agit(root, "checkout", "-q", "-b", "elsewhere")
    write(root, GUIDE, "shadow\n")
    await agit(root, "commit", "-q", "-am", "shadow")
    await agit(root, "tag", "refs/heads/main", "elsewhere")
    facts = GitFacts()
    assert await facts.show_on_base(root, GUIDE) == ("master", "real\n")
    # HEAD is `elsewhere`: a tag taken for the base would make the fork point HEAD itself.
    assert (await facts.fork(root, None)).base == await agit(root, "rev-parse", "master")
