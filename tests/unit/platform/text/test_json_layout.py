import json
import math
from pathlib import Path
from typing import Any

import pytest

from code_factory.platform.text import Style, render

FORMATS = Path(__file__).resolve().parents[3] / "support/golden" / "formats" / "json"
CASES = json.loads((FORMATS / "cases.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((FORMATS / "cases.golden.json").read_text(encoding="utf-8"))
STYLE_KEYS = {Style.DEFAULT: "default", Style.COMPACT: "compact", Style.INDENT2: "indent"}


@pytest.mark.parametrize("style", list(Style))
@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_every_golden_string(case: dict[str, Any], style: Style) -> None:
    assert render(case["value"], style) == GOLDEN[case["name"]][STYLE_KEYS[style]]


def test_default_style_is_the_default() -> None:
    assert render({"a": [1, 2]}) == '{"a": [1, 2]}'


def test_empty_containers_stay_on_one_line_when_indented() -> None:
    assert render({"a": [], "b": {}}, Style.INDENT2) == '{\n  "a": [],\n  "b": {}\n}'


def test_an_astral_character_is_a_surrogate_pair() -> None:
    assert render("\U0001f680") == '"\\ud83d\\ude80"'


def test_a_control_character_is_escaped() -> None:
    assert render("\x00\x1f\x7f") == '"\\u0000\\u001f\\u007f"'


def test_non_finite_floats_are_written_as_javascript_names() -> None:
    assert render([math.nan, math.inf, -math.inf]) == "[NaN, Infinity, -Infinity]"


def test_no_trailing_newline() -> None:
    assert not render({"a": 1}, Style.INDENT2).endswith("\n")
