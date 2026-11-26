"""Eval variants apply real repository settings in separate checkouts."""

import json
import subprocess
import sys
from pathlib import Path

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
