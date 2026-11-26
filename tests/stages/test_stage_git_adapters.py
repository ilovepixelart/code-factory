"""The stage adapters against a real temporary git repository with an origin, and the test file
reader against a real folder. Expected values are worked by hand from the repository each test
builds."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from code_factory.stages.adapters import GitDiffReader, GitRunner, TestFiles, files
from stage_git import clone_with_origin, commit, git


@pytest.fixture
def work(tmp_path: Path) -> Path:
    return clone_with_origin(tmp_path)


async def test_every_variable_naming_a_repository_is_removed_from_what_git_runs_with(
    work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("GIT_DIR", "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_WORK_TREE"):
        monkeypatch.setenv(name, str(tmp_path / "elsewhere"))
    head = git(work, "rev-parse", "HEAD")

    assert await GitDiffReader(work).same_code(head, head)
    assert await GitDiffReader(work).fork_point(head) is not None
    assert os.environ["GIT_COMMON_DIR"] == str(tmp_path / "elsewhere")


async def test_git_is_started_from_the_program_the_runner_was_given_and_never_from_another(
    work: Path,
) -> None:
    missing = GitRunner(program=Path("/nonexistent/git"))

    assert await missing.run(work, "rev-parse", "HEAD") is None


async def test_the_program_git_is_found_in_a_folder_only_trusted_users_write(work: Path) -> None:
    done = await GitRunner().run(work, "rev-parse", "--is-inside-work-tree")

    assert done is not None
    assert (done.code, done.text.strip()) == (0, "true")


async def test_the_diff_reader_finds_the_fork_point_and_the_diff_since_it(work: Path) -> None:
    base = git(work, "rev-parse", "HEAD")
    git(work, "checkout", "-b", "feat/CF-1")
    commit(work, "one", "src/a.py")
    head = commit(work, "two", "src/b.py")
    reader = GitDiffReader(work)

    assert await reader.fork_point(head) == base
    raw = await reader.diff(base, head, "--raw")
    stat = await reader.diff(base, head, "--numstat")
    assert raw is not None
    assert raw.count("\0") == 4
    assert stat == "1\t0\tsrc/a.py\x001\t0\tsrc/b.py\x00"


async def test_a_diff_of_unknown_commits_is_unreadable_not_empty(work: Path) -> None:
    reader = GitDiffReader(work)

    assert await reader.diff("0" * 40, "f" * 40, "--raw") is None
    assert await reader.fork_point("f" * 40) is None


async def test_a_revision_that_looks_like_an_option_is_never_read_as_one(
    work: Path, tmp_path: Path
) -> None:
    head = git(work, "rev-parse", "HEAD")
    target = tmp_path / "pwned"

    assert await GitDiffReader(work).diff(f"--output={target}", head, "--raw") is None
    assert await GitDiffReader(work).same_code(head, f"--output={target}") is False
    assert not [name for name in os.listdir(tmp_path) if name.startswith("pwned")]  # noqa: PTH208


async def test_the_default_base_prefers_the_remote_branch_and_falls_back_to_the_local_one(
    work: Path, tmp_path: Path
) -> None:
    assert await GitDiffReader(work).default_base() == "refs/remotes/origin/main"
    lone = tmp_path / "lone"
    lone.mkdir()
    git(lone, "init", "--initial-branch=main")
    commit(lone, "only", "a.txt")

    assert await GitDiffReader(lone).default_base() == "refs/heads/main"


async def test_the_same_code_is_the_commit_itself_or_a_later_one_with_no_change_or_merge(
    work: Path,
) -> None:
    first = git(work, "rev-parse", "HEAD")
    git(work, "checkout", "-b", "feat/CF-1")
    quiet = commit(work, "no file changes")
    changed = commit(work, "a file", "src/a.py")
    reader = GitDiffReader(work)

    assert await reader.same_code(first, first)
    assert await reader.same_code(first, quiet)
    assert not await reader.same_code(first, changed)
    assert not await reader.same_code(changed, first)
    assert not await reader.same_code("", changed)
    assert not await reader.same_code("f" * 40, changed)


async def test_a_merge_between_two_commits_is_not_the_same_code_even_when_the_tree_is_kept(
    work: Path,
) -> None:
    git(work, "checkout", "-b", "side")
    commit(work, "side", "side.txt")
    git(work, "checkout", "main")
    start = git(work, "rev-parse", "HEAD")
    git(work, "merge", "--no-ff", "-s", "ours", "-m", "keep our tree", "side")
    merged = git(work, "rev-parse", "HEAD")

    assert not await GitDiffReader(work).same_code(start, merged)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "wt"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_a.py").write_text("def test_a():\n    pass\n")
    (root / ".hidden").mkdir()
    (root / ".hidden" / "test_h.py").write_text("def test_h():\n    pass\n")
    (tmp_path / "outside.py").write_text("def test_out():\n    pass\n")
    return root


async def test_the_test_files_a_pattern_matches_are_read_with_their_text(tree: Path) -> None:
    found = await TestFiles(tree).read(["tests/*.py", "no/such/*.py"])

    assert found.files == {"tests/test_a.py": "def test_a():\n    pass\n"}
    assert found.unmatched == ["no/such/*.py"]


async def test_a_pattern_may_match_a_dotfile_folder(tree: Path) -> None:
    found = await TestFiles(tree).read(["**/test_h.py"])

    assert list(found.files) == [".hidden/test_h.py"]


@pytest.mark.parametrize(
    "pattern",
    ["/etc/passwd", "../outside.py", "tests/../../outside.py", "tests/../tests/test_a.py"],
)
async def test_a_pattern_leaving_the_root_is_refused_and_tells_nothing(
    tree: Path, pattern: str
) -> None:
    found = await TestFiles(tree).read([pattern])

    assert found.files == {}
    assert found.unmatched == [pattern]


async def test_an_absolute_pattern_is_refused_even_when_it_names_a_file_inside_the_root(
    tree: Path,
) -> None:
    inside = str(tree / "tests" / "test_a.py")

    found = await TestFiles(tree).read([inside])

    assert found.files == {}
    assert found.unmatched == [inside]


async def test_a_link_that_leaves_the_root_is_not_followed(tree: Path, tmp_path: Path) -> None:
    (tree / "tests" / "test_link.py").symlink_to(tmp_path / "outside.py")
    (tree / "tests" / "test_dead.py").symlink_to(tmp_path / "missing.py")

    found = await TestFiles(tree).read(["tests/test_link.py", "tests/test_dead.py"])

    assert found.files == {}
    assert found.unmatched == ["tests/test_link.py", "tests/test_dead.py"]


async def test_the_scan_stops_reading_files_once_its_deadline_has_passed(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("b", "c"):
        (tree / "tests" / f"test_{name}.py").write_text(f"def test_{name}():\n    pass\n")
    clock = [0.0]
    real = files._read
    reads: list[Path] = []

    def read_then_expire(path: Path) -> str | None:
        reads.append(path)
        clock[0] = 1e9
        return real(path)

    monkeypatch.setattr(files, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(files, "_read", read_then_expire)

    found = await TestFiles(tree).read(["tests/*.py"])

    assert len(reads) == 1
    assert len(found.files) == 1


def test_a_recursive_pattern_matching_nothing_stops_walking_at_its_deadline(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for number in range(40):
        (tree / "tests" / f"dir{number}").mkdir()
    scanned: list[str] = []
    real = os.scandir

    def counting(path: str) -> os._ScandirIterator[str]:
        scanned.append(path)
        return real(path)

    monkeypatch.setattr(os, "scandir", counting)

    found = files._matches(tree.resolve(), "**/nomatch.py", deadline=0.0)

    assert found == []
    assert len(scanned) <= 2


def test_a_recursive_pattern_finds_the_files_below_every_folder(tree: Path) -> None:
    (tree / "tests" / "deep" / "er").mkdir(parents=True)
    (tree / "tests" / "deep" / "er" / "test_d.py").write_text("x")
    (tree / "test_top.py").write_text("x")

    found = files._matches(tree.resolve(), "**/test_*.py", deadline=float("inf"))

    assert sorted(found) == [
        ".hidden/test_h.py",
        "test_top.py",
        "tests/deep/er/test_d.py",
        "tests/test_a.py",
    ]


async def test_a_pattern_that_matches_only_a_folder_matches_no_file(tree: Path) -> None:
    found = await TestFiles(tree).read(["tests"])

    assert found.files == {}
    assert found.unmatched == ["tests"]


async def test_a_double_star_does_not_cross_a_link_to_a_folder(tree: Path) -> None:
    (tree / "linked").symlink_to(tree / "tests", target_is_directory=True)

    found = await TestFiles(tree).read(["**/test_a.py"])

    assert list(found.files) == ["tests/test_a.py"]


async def test_an_unreadable_file_is_skipped_and_a_long_one_is_cut(tree: Path) -> None:
    locked = tree / "tests" / "test_locked.py"
    locked.write_text("x")
    locked.chmod(0)
    (tree / "tests" / "test_big.py").write_text("y" * (1024 * 1024 + 10))
    try:
        found = await TestFiles(tree).read(["tests/test_locked.py", "tests/test_big.py"])
    finally:
        locked.chmod(0o600)

    assert "tests/test_locked.py" not in found.files
    assert len(found.files["tests/test_big.py"]) == 1024 * 1024
