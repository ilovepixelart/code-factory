"""The adapters: the repository's documents, the names of its tests, its address on the web."""

import asyncio
from pathlib import Path

import pytest

from code_factory.memory_extras.adapters import (
    DefinedTests,
    OriginWeb,
    RepositoryFiles,
    is_test_file,
    names_in_test_file,
)
from code_factory.platform.errors import UnavailableError
from memory_extras_fakes import FakeGit

ROOT = Path("/repos/sample")
PYTEST_FILE = "def helper():\n    pass\n\n\ndef test_a_form_post_changes_nothing():\n    pass\n"


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_x.py", "pkg/test_x.py", "pkg/x_test.py", "pkg/x_test.go", "web/a.test.ts",
        "web/a.spec.js", "web/e2e/board.ts", "tests/helpers.py", "crates/core/src/lib.rs",
        "pkg/__tests__/a.js", "spec/a.rb.js",
    ],
)  # fmt: skip
def test_a_file_is_read_for_tests_by_its_name_or_its_folder_and_every_rust_file_is(
    path: str,
) -> None:
    assert is_test_file(path)


@pytest.mark.parametrize("path", ["src/app.py", "web/src/App.vue", "pkg/latest.py", "pkg/x.ts"])
def test_a_source_file_outside_a_test_folder_is_not_read_for_tests(path: str) -> None:
    assert not is_test_file(path)


def test_names_come_from_the_languages_own_markers() -> None:
    assert names_in_test_file("t/test_a.py", PYTEST_FILE) == ["test_a_form_post_changes_nothing"]
    assert names_in_test_file("a.rs", "#[test]\nfn rust_one() {}\nfn helper() {}\n") == ["rust_one"]
    assert names_in_test_file("a_test.go", "func TestOne(t *T) {}\nfunc helper() {}\n") == [
        "TestOne"
    ]
    assert names_in_test_file("a.test.ts", "it('one_name', () => {})\n") == ["one_name"]


async def test_a_test_a_file_defines_is_a_defined_name_and_a_helper_is_not() -> None:
    git = FakeGit({"tests/test_a.py": PYTEST_FILE, "src/lib.py": "def test_hidden():\n    pass\n"})
    names = await DefinedTests(git).defined("sample", ROOT)
    assert names == {"test_a_form_post_changes_nothing"}


async def test_a_second_call_on_the_same_head_lists_nothing_again() -> None:
    git = FakeGit({"tests/test_a.py": PYTEST_FILE})
    tests = DefinedTests(git)
    first = await tests.defined("sample", ROOT)
    second = await tests.defined("sample", ROOT)
    assert first == second
    assert git.calls["tracked_files"] == 1


async def test_a_new_head_lists_the_tests_again() -> None:
    git = FakeGit({"tests/test_a.py": PYTEST_FILE})
    tests = DefinedTests(git)
    await tests.defined("sample", ROOT)
    git.head = "c2"
    git.files["tests/test_b.py"] = "def test_b():\n    pass\n"
    assert await tests.defined("sample", ROOT) == {"test_a_form_post_changes_nothing", "test_b"}
    assert git.calls["tracked_files"] == 2


async def test_callers_arriving_together_cause_one_listing() -> None:
    git = FakeGit({"tests/test_a.py": PYTEST_FILE})
    tests = DefinedTests(git)
    found = await asyncio.gather(*(tests.defined("sample", ROOT) for _ in range(5)))
    assert all(names == found[0] for names in found)
    assert git.calls["tracked_files"] == 1


async def test_only_the_last_eight_repositories_are_remembered() -> None:
    git = FakeGit({"tests/test_a.py": PYTEST_FILE})
    tests = DefinedTests(git)
    for number in range(9):
        await tests.defined(f"repo{number}", ROOT)
    await tests.defined("repo8", ROOT)
    assert git.calls["tracked_files"] == 9
    await tests.defined("repo0", ROOT)
    assert git.calls["tracked_files"] == 10


async def test_an_unreadable_repository_has_no_tests_and_is_not_remembered() -> None:
    git = FakeGit({"tests/test_a.py": PYTEST_FILE})
    git.fail = UnavailableError("git is busy")
    tests = DefinedTests(git)
    assert await tests.defined("sample", ROOT) == frozenset()
    git.fail = None
    assert await tests.defined("sample", ROOT) == {"test_a_form_post_changes_nothing"}


async def test_an_unborn_branch_is_listed_every_time_because_it_has_no_head_to_key_on() -> None:
    git = FakeGit({"tests/test_a.py": PYTEST_FILE}, head="")
    tests = DefinedTests(git)
    await tests.defined("sample", ROOT)
    await tests.defined("sample", ROOT)
    assert git.calls["tracked_files"] == 2


async def test_the_claude_file_is_read_and_a_missing_one_is_empty() -> None:
    assert await RepositoryFiles(FakeGit({"CLAUDE.md": "# Rules\n"})).claude_md(ROOT) == "# Rules\n"
    assert await RepositoryFiles(FakeGit()).claude_md(ROOT) == ""


async def test_an_unreadable_claude_file_is_empty() -> None:
    git = FakeGit({"CLAUDE.md": "x"})
    git.fail = UnavailableError("busy")
    assert await RepositoryFiles(git).claude_md(ROOT) == ""


async def test_the_knowledge_files_are_the_readme_claude_and_the_docs() -> None:
    git = FakeGit(
        {
            "README.md": "readme",
            "CLAUDE.md": "claude",
            "docs/a.md": "doc a",
            "docs/deep/b.md": "doc b",
            "src/notes.md": "not read",
            "docs/image.png": "not read",
        }
    )
    docs = await RepositoryFiles(git).knowledge_files("sample", ROOT)
    assert [(d.path, d.text) for d in docs] == [
        ("CLAUDE.md", "claude"),
        ("README.md", "readme"),
        ("docs/a.md", "doc a"),
        ("docs/deep/b.md", "doc b"),
    ]


async def test_one_unreadable_document_does_not_hide_the_readable_ones() -> None:
    git = FakeGit({"README.md": "readme", "CLAUDE.md": "claude", "docs/a.md": "doc a"})
    git.unreadable = {"CLAUDE.md"}
    docs = await RepositoryFiles(git).knowledge_files("sample", ROOT)
    assert [(d.path, d.text) for d in docs] == [("README.md", "readme"), ("docs/a.md", "doc a")]


async def test_one_unreadable_test_file_does_not_hide_the_names_of_the_others() -> None:
    git = FakeGit({"tests/test_a.py": PYTEST_FILE, "tests/test_b.py": "def test_b():\n    pass\n"})
    git.unreadable = {"tests/test_b.py"}
    assert await DefinedTests(git).defined("sample", ROOT) == {"test_a_form_post_changes_nothing"}


async def test_cites_that_exist_below_the_root_are_found_and_others_are_not(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "kept.py").write_text("x", encoding="utf-8")
    (tmp_path.parent / "outside.txt").write_text("x", encoding="utf-8")
    cites = ["src/kept.py", "src/gone.py", "../outside.txt", "/etc/hosts", "a_test"]
    found = await RepositoryFiles(FakeGit()).cites_exist(tmp_path, cites)
    assert found == {"src/kept.py"}


async def test_the_web_address_is_read_from_origin_and_remembered_for_fifteen_seconds() -> None:
    git = FakeGit()
    git.remote = "git@github.com:owner/name.git"
    now = [100.0]
    origin = OriginWeb(git, clock=lambda: now[0])
    assert await origin.web("sample") == "https://github.com/owner/name"
    now[0] = 114.9
    assert await origin.web("sample") == "https://github.com/owner/name"
    assert git.calls["remote_url"] == 1
    now[0] = 115.0
    git.remote = "https://github.com/owner/other"
    assert await origin.web("sample") == "https://github.com/owner/other"
    assert git.calls["remote_url"] == 2


async def test_a_remote_that_is_not_github_has_no_web_address() -> None:
    git = FakeGit()
    git.remote = "https://example.org/a/b"
    assert await OriginWeb(git).web("sample") == ""
    assert await OriginWeb(FakeGit()).web("sample") == ""


async def test_a_large_listing_is_parsed_in_a_process_and_names_the_same_tests() -> None:
    big = "# padding\n" * 60000 + "\ndef test_far_down():\n    pass\n"
    git = FakeGit({"tests/test_big.py": big, "tests/test_a.py": PYTEST_FILE})
    tests = DefinedTests(git)
    try:
        assert await tests.defined("sample", ROOT) == {
            "test_far_down",
            "test_a_form_post_changes_nothing",
        }
        assert tests._pool is not None
    finally:
        await tests.close()
