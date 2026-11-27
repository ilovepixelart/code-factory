"""Owner-run red checks and verification of their locked test files."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from git_support import commit, make_repo, write

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gate_spec_lock.py"
TEST = "tests/test_feature.py"
NODE = f"{TEST}::test_contract"
EXPECTED = "the new contract must hold"


def spec_lock(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # the checked-in tool over a disposable repo
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_an_expected_assertion_locks_the_test_file_against_edits(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    commit(
        repo,
        "Define the spec check",
        **{TEST: f"def test_contract():\n    assert False, {EXPECTED!r}\n"},
    )
    receipt = str(tmp_path / "receipt.json")

    sealed = spec_lock(repo, "seal", receipt, "--check", NODE, EXPECTED)

    assert sealed.returncode == 0, sealed.stderr
    assert spec_lock(repo, "verify", receipt).returncode == 0
    assert spec_lock(repo, "seal", receipt, "--check", NODE, EXPECTED).returncode == 2
    write(repo, TEST, "def test_contract():\n    assert True\n")
    changed = spec_lock(repo, "verify", receipt)
    assert changed.returncode == 1
    assert TEST in changed.stdout


@pytest.mark.parametrize(
    "body",
    [
        "assert True",
        "assert False, 'a different failure'",
        f"raise ValueError({EXPECTED!r})",
    ],
)
def test_only_the_expected_assertion_can_create_a_lock(tmp_path: Path, body: str) -> None:
    repo = make_repo(tmp_path)
    commit(repo, "Define the spec check", **{TEST: f"def test_contract():\n    {body}\n"})
    receipt = tmp_path / "receipt.json"

    result = spec_lock(repo, "seal", str(receipt), "--check", NODE, EXPECTED)

    assert result.returncode == 1, result.stderr
    assert not receipt.exists()


def test_a_manifest_seals_multiple_named_checks(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    other_file = "tests/test_other.py"
    other_message = "the second requirement must hold"
    commit(
        repo,
        "Define two spec checks",
        **{
            TEST: f"def test_contract():\n    assert False, {EXPECTED!r}\n",
            other_file: f"def test_other():\n    assert False, {other_message!r}\n",
        },
    )
    manifest = tmp_path / "checks.toml"
    manifest.write_text(
        f"[[checks]]\nnode = {NODE!r}\nreason = {EXPECTED!r}\n\n"
        f"[[checks]]\nnode = '{other_file}::test_other'\nreason = {other_message!r}\n"
    )
    receipt = str(tmp_path / "receipt.json")

    sealed = spec_lock(repo, "seal", receipt, "--manifest", str(manifest))

    assert sealed.returncode == 0, sealed.stderr
    assert spec_lock(repo, "verify", receipt).returncode == 0
    write(repo, other_file, "def test_other():\n    assert True\n")
    changed = spec_lock(repo, "verify", receipt)
    assert changed.returncode == 1
    assert other_file in changed.stdout


def test_a_malformed_manifest_is_rejected_before_running_any_case(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    commit(
        repo,
        "Define a spec check",
        **{
            TEST: (
                "def test_contract():\n"
                "    from pathlib import Path\n"
                "    Path('ran').touch()\n"
                f"    assert False, {EXPECTED!r}\n"
            ),
        },
    )
    manifest = tmp_path / "checks.toml"
    manifest.write_text(
        f"[[checks]]\nnode = {NODE!r}\nreason = {EXPECTED!r}\n\n"
        "[[checks]]\nnode = 'tests/test_bad.py::test_bad'\n"
    )
    receipt = tmp_path / "receipt.json"

    result = spec_lock(repo, "seal", str(receipt), "--manifest", str(manifest))

    assert result.returncode == 2
    assert "checks[2]" in result.stderr
    assert not (repo / "ran").exists()
    assert not receipt.exists()


def test_prove_reports_locked_files_for_the_runner_to_publish(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    head = commit(
        repo,
        "Define the spec check",
        **{TEST: f"def test_contract():\n    assert False, {EXPECTED!r}\n"},
    )

    result = spec_lock(repo, "prove", "--check", NODE, EXPECTED)

    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["commit"] == head
    assert list(receipt["files"]) == [TEST]
