"""Eval variants apply real repository settings in separate checkouts."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from git_support import commit, make_repo

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_pipeline.py"


def test_each_variant_gets_the_same_tree_and_its_own_pipeline_settings(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    settings = "[agents]\nreview_roles = ['security', 'qa']\nslots = 2\n"
    head = commit(repo, "Set the review roles", **{".code-factory/config.toml": settings})
    manifest = tmp_path / "matrix.toml"
    manifest.write_text(
        "[[setup]]\nname = 'baseline'\n[setup.steps]\nqa = true\n"
        "[[setup]]\nname = 'without-qa'\n[setup.steps]\nqa = false\n"
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import os,tomllib\n"
        "from pathlib import Path\n"
        "agents = tomllib.loads(Path('.code-factory/config.toml').read_text())['agents']\n"
        "assert agents['slots'] == 2\n"
        "assert agents['ship'] is False\n"
        "baseline = os.environ['CODE_FACTORY_EVAL_SETUP'] == 'baseline'\n"
        "expected = ['security','qa'] if baseline else ['security']\n"
        "assert agents['review_roles'] == expected\n"
    )
    report = tmp_path / "report.json"

    result = subprocess.run(  # noqa: S603  # checked-in runner and a harmless fixture driver
        [sys.executable, str(SCRIPT), str(manifest), str(report), sys.executable, str(driver)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    records = json.loads(report.read_text())
    assert [(row["name"], row["head"], row["exit_code"]) for row in records] == [
        ("baseline", head, 0),
        ("without-qa", head, 0),
    ]
    assert (repo / ".code-factory/config.toml").read_text() == settings


TRIAL = """
[fix_round_trial]
cases = ["simple", "third-round", "unknown-owner-cost"]

[[setup]]
name = "three"
fix_rounds = 3

[[setup]]
name = "two"
fix_rounds = 2
"""


def trial(
    repo: Path, folder: Path, driver_source: str, manifest_source: str = TRIAL
) -> tuple[subprocess.CompletedProcess[str], Path]:
    manifest = folder / "matrix.toml"
    manifest.write_text(manifest_source)
    driver = folder / "driver.py"
    driver.write_text(driver_source)
    report = folder / "report.json"
    result = subprocess.run(  # noqa: S603  # checked-in runner and a harmless fixture driver
        [sys.executable, str(SCRIPT), str(manifest), str(report), sys.executable, str(driver)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, report


DRIVER = """
import json, os, tomllib
from pathlib import Path

agents = tomllib.loads(Path(".code-factory/config.toml").read_text())["agents"]
cap = agents["fix_rounds"]
assert agents["review_rounds"] == 5
assert agents["ship"] is False
assert agents["merge_approval"] is True
assert json.loads(os.environ["CODE_FACTORY_EVAL_CASES"]) == [
    "simple", "third-round", "unknown-owner-cost"
]

def row(case_id, state, rounds, agent, owner):
    return dict(case_id=case_id, state=state, fix_rounds=rounds,
                agent_cost_cents=agent, owner_cost_cents=owner)

results = [
    row("unknown-owner-cost", "closed", cap, 50, None if cap == 3 else 5),
    row("third-round", "merged" if cap == 3 else "open", cap, cap * 100, 40),
    row("simple", "merged", 1, cap * 10, 0),
]
Path(os.environ["CODE_FACTORY_EVAL_OUTCOMES"]).write_text(json.dumps(results))
"""


def test_fix_round_trial_compares_the_same_cases_in_both_isolated_arms(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    settings = "[agents]\nfix_rounds = 9\nreview_rounds = 5\n"
    head = commit(repo, "Set the original caps", **{".code-factory/config.toml": settings})

    result, report = trial(repo, tmp_path, DRIVER)

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(report.read_text())
    assert data["cases"] == ["simple", "third-round", "unknown-owner-cost"]
    assert [(run["fix_rounds"], run["head"]) for run in data["runs"]] == [(3, head), (2, head)]
    assert all([row["case_id"] for row in run["outcomes"]] == data["cases"] for run in data["runs"])
    assert data["comparison"]["arms"] == [
        {"fix_rounds": 2, "merged": 1, "closed": 1, "open": 1, "rounds_used": 5},
        {"fix_rounds": 3, "merged": 2, "closed": 1, "open": 0, "rounds_used": 7},
    ]
    assert data["comparison"]["merges"] == {
        "both": ["simple"],
        "two_only": [],
        "three_only": ["third-round"],
        "neither": ["unknown-owner-cost"],
    }
    assert data["comparison"]["cost"] == {
        "paired_cases": ["simple", "third-round"],
        "three_minus_two_cents": 110,
    }
    assert (repo / ".code-factory/config.toml").read_text() == settings


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("results.pop()", "did not return exactly one outcome per named case"),
        ("results.append(results[0])", "did not return exactly one outcome per named case"),
        ("results[1] = results[0]", "did not return exactly one outcome per named case"),
        ("results[0]['fix_rounds'] = 4", "invalid fix-round count"),
        ("results[0]['owner_cost_cents'] = True", "invalid owner_cost_cents"),
    ],
)
def test_an_incomplete_or_invalid_trial_has_no_comparison(
    tmp_path: Path, mutation: str, error: str
) -> None:
    repo = make_repo(tmp_path)
    commit(repo, "Set the review cap", **{".code-factory/config.toml": "[agents]\nreview_rounds=5"})
    source = DRIVER.replace(
        'Path(os.environ["CODE_FACTORY_EVAL_OUTCOMES"])',
        f'{mutation}\nPath(os.environ["CODE_FACTORY_EVAL_OUTCOMES"])',
    )

    result, report = trial(repo, tmp_path, source)

    assert result.returncode == 1, result.stdout + result.stderr
    data = json.loads(report.read_text())
    assert data["comparison"] is None
    assert all(error in run["outcomes_error"] for run in data["runs"])


@pytest.mark.parametrize(
    "manifest",
    [
        TRIAL.replace("fix_rounds = 3", "fix_rounds = 4"),
        TRIAL.replace(
            'name = "two"\nfix_rounds = 2', 'name = "two"\nfix_rounds = 2\n[setup.steps]\nqa=true'
        ),
    ],
)
def test_a_trial_only_varies_two_and_three_fix_rounds(tmp_path: Path, manifest: str) -> None:
    result, report = trial(make_repo(tmp_path), tmp_path, "raise RuntimeError('ran')", manifest)

    assert result.returncode == 2
    assert "the fix-round trial needs caps 2 and 3 with identical step settings" in result.stderr
    assert not report.exists()
