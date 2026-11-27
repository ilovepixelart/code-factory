"""The factory routes' catalogued shapes hold the hand-written answers and refuse a drifted one."""

import json
from typing import Any

import pytest

from contract_catalogue import ROUTES
from contract_shapes import conforms
from repo_files import ROOT

GOLDEN = json.loads(
    (ROOT / "tests" / "support" / "golden" / "factory" / "dashboard.golden.json").read_text()
)


def shape_of_route(path: str) -> Any:  # noqa: ANN401
    (route,) = (r for r in ROUTES if r.path == path)
    assert route.shape is not None
    return route.shape()


def test_the_dashboard_shape_accepts_the_golden_answer() -> None:
    assert conforms(GOLDEN, shape_of_route("/api/factory/dashboard")) == []


def test_the_dashboard_shape_accepts_the_empty_answer_of_the_null_providers() -> None:
    empty = {
        "from": 1.0,
        "to": 2.0,
        "now": 3.0,
        "runs": {k: ([] if k.startswith("by_") else 0) for k in GOLDEN["runs"]},
        "prs": dict.fromkeys(GOLDEN["prs"], 0),
        "series": {"bucket": "day", "points": []},
        "autonomy": {"share": None, "autonomous": 0, "assisted": 0, "unknown": 0},
        "cycle": {"total": {"median": None, "count": 0}, "stages": []},
        "cost": {**GOLDEN["cost"], "median": None, "by_component": [], "by_size": []},
        "merged_cost": {**GOLDEN["merged_cost"], "merged": 0},
        "expensive": [],
        "scorers": {"available": False, "cards": []},
        "improvements": {"available": False, "items": []},
        "fix_rounds": [],
        "role_notes": [],
    }
    assert conforms(empty, shape_of_route("/api/factory/dashboard")) == []


def test_the_expensive_scorer_and_runs_shapes_accept_the_goldens_parts() -> None:
    assert (
        conforms({"prs": GOLDEN["expensive"]}, shape_of_route("/api/factory/prs/expensive")) == []
    )
    assert conforms(GOLDEN["scorers"], shape_of_route("/api/factory/scorers")) == []
    assert conforms(GOLDEN["runs"], shape_of_route("/api/factory/runs")) == []
    assert conforms(GOLDEN["improvements"], shape_of_route("/api/factory/improvements")) == []


def test_the_improvements_shape_accepts_an_item_of_the_spec_example() -> None:
    answer = {
        "available": True,
        "items": [
            {
                "url": "u",
                "number": 21,
                "title": "t",
                "state": "open",
                "opened_at": 1794000000,
                "failures": 25,
            }
        ],
    }
    assert conforms(answer, shape_of_route("/api/factory/improvements")) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda d: d["cost"].pop("measurement"), "missing key `measurement`"),
        (lambda d: d["prs"].update(extra=1), "unexpected key `extra`"),
        (lambda d: d["autonomy"].update(share="x"), "expected number or null, got string"),
        (lambda d: d["expensive"][0].update(cost=None), "expected number, got null"),
    ],
)
def test_the_dashboard_shape_refuses_a_drifted_answer(change: Any, problem: str) -> None:  # noqa: ANN401
    drifted = json.loads(json.dumps(GOLDEN))
    change(drifted)
    assert any(
        problem in line for line in conforms(drifted, shape_of_route("/api/factory/dashboard"))
    )
