import subprocess
import sys
from pathlib import Path

from git_support import commit, git, make_repo, write

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gate_delta.py"


def delta(repo: Path, action: str = "review") -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # run the checked-in gate helper against the fixture
        [sys.executable, str(SCRIPT), action, "--base", "origin/main"],
        cwd=repo,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def test_gate_delta_finds_deleted_cases_and_added_skips_from_the_branch_base(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    commit(
        repo,
        "Test behaviour",
        **{
            "tests/test_feature.py": (
                "def test_kept():\n    assert True\n\ndef test_removed():\n    assert True\n"
            ),
        },
    )
    git(repo, "push", "origin", "main")
    git(repo, "switch", "-c", "feature")
    write(
        repo,
        "tests/test_feature.py",
        "import pytest\n\n@pytest.mark.skip\ndef test_kept():\n    assert True\n",
    )

    result = delta(repo)

    assert result.returncode == 1
    assert "test_removed" in result.stdout
    assert "new skip" in result.stdout


def test_a_test_file_moved_with_its_skip_is_not_a_new_skip(tmp_path: Path) -> None:
    source = "import pytest\n\n@pytest.mark.skip\ndef test_kept():\n    assert True\n"
    repo = make_repo(tmp_path)
    commit(repo, "Skipped test", **{"tests/test_feature.py": source})
    git(repo, "push", "origin", "main")
    git(repo, "switch", "-c", "feature")
    git(repo, "mv", "tests/test_feature.py", "tests/test_moved.py")

    moved = delta(repo)
    write(repo, "tests/test_other.py", source.replace("test_kept", "test_other"))
    added = delta(repo)

    assert (moved.returncode, moved.stdout) == (0, "")
    assert added.returncode == 1
    assert "'tests/test_other.py' adds a new skip" in added.stdout


def test_gate_delta_warns_on_assertion_reduction_without_blocking(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    commit(
        repo,
        "Assert two properties",
        **{
            "tests/test_feature.py": "def test_kept():\n    assert True\n    assert False\n",
        },
    )
    git(repo, "push", "origin", "main")
    write(repo, "tests/test_feature.py", "def test_kept():\n    assert True\n")
    write(repo, "AGENTS.md", "Line\n" * 101)

    result = delta(repo)

    assert result.returncode == 0
    assert "fewer assertion lines" in result.stdout
    assert "AGENTS.md has 101 lines" in result.stdout


def test_gate_delta_selects_module_tests_and_broadens_for_shared_inputs(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    commit(
        repo,
        "Module",
        **{
            "src/code_factory/talk/rules.py": "value = 1\n",
            "tests/unit/talk/test_rules.py": "def test_value():\n    assert True\n",
            "tests/integration/talk/test_store.py": "def test_stored():\n    assert True\n",
            "tests/e2e/talk/test_served.py": "def test_served():\n    assert True\n",
        },
    )
    git(repo, "push", "origin", "main")
    write(repo, "src/code_factory/talk/rules.py", "value = 2\n")
    assert delta(repo, "affected").stdout.splitlines() == [
        "python tests/integration/talk",
        "python tests/unit/talk",
    ]
    write(repo, "conftest.py", "# shared\n")
    assert delta(repo, "affected").stdout.splitlines() == ["full"]


def test_affected_gate_delta_changes_select_only_its_test_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo, "scripts/gate_delta.py", "# changed\n")
    write(repo, "tests/integration/test_gate_delta.py", "def test_gate():\n    assert True\n")

    assert delta(repo, "affected").stdout.splitlines() == [
        "python tests/integration/test_gate_delta.py"
    ]


def test_delta_coverage_rejects_a_new_file_missing_from_both_reports(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo, "src/code_factory/new.py", "answer = 42\n")
    python = tmp_path / "python.json"
    python.write_text('{"files": {}}')
    vue = tmp_path / "lcov.info"
    vue.write_text("")
    result = subprocess.run(  # noqa: S603  # execute the checked-in reporter
        [
            sys.executable,
            str(SCRIPT.with_name("gate_coverage.py")),
            git(repo, "rev-parse", "HEAD"),
            str(python),
            str(vue),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "'src/code_factory/new.py' is missing from the report" in result.stdout
