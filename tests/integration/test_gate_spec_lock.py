"""Owner-run red checks and verification of their locked test files."""

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
