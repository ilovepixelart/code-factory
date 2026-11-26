"""The optional mutation check runs only changed source in a disposable checkout."""

import subprocess
import sys
from pathlib import Path

import pytest

from git_support import commit, git, make_repo, write

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gate_mutation.py"
SOURCE = "src/code_factory/demo/rules.py"


@pytest.mark.parametrize(
    ("assertion", "outcome"),
    [("isinstance(label(8), str)", "survived"), ("label(8) == 'small'", "was caught")],
)
def test_mutation_checks_the_disposable_copy_and_leaves_the_branch_alone(
    tmp_path: Path, assertion: str, outcome: str
) -> None:
    repo = make_repo(tmp_path)
    base = """def label(amount):
    return 'old'

def unrelated():
    return True
"""
    write(repo, "src/code_factory/__init__.py", "")
    write(repo, "src/code_factory/demo/__init__.py", "")
    commit(
        repo,
        "Create a module and its test",
        **{
            SOURCE: base,
            "tests/demo/test_rules.py": (
                "from code_factory.demo.rules import label\n"
                f"def test_label():\n    assert {assertion}\n"
            ),
        },
    )
    base_sha = git(repo, "rev-parse", "HEAD")
    changed = base.replace("return 'old'", "return 'small' if amount < 10 else 'large'")
    commit(repo, "Adjust the label boundary", **{SOURCE: changed})

    result = subprocess.run(  # noqa: S603  # run the checked-in helper over a test repository
        [sys.executable, str(SCRIPT), base_sha],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"{SOURCE}:2 {outcome}" in result.stdout
    assert f"{SOURCE}:5" not in result.stdout
    assert (repo / SOURCE).read_text() == changed
    assert not git(repo, "status", "--porcelain")
