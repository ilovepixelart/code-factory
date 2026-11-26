"""What the text helpers borrow from the standard library: each test fails if Python changes it."""

import fnmatch
import json
import random
import shlex
from pathlib import Path

import pytest
from starlette.responses import JSONResponse

from growth import LINEAR_BOUND, growth

GOLDEN = Path(__file__).resolve().parents[2] / "golden" / "formats"

# The classes the previous implementation wrote out, as explicit code points.
WHITESPACE = {
    *range(9, 14), *range(28, 33), 133, 160, 5760, *range(8192, 8203), 8232, 8233, 8239, 8287,
    12288,
}  # fmt: skip
LINE_BREAKS = {10, 13, 11, 12, 28, 29, 30, 133, 0x2028, 0x2029}


def test_whitespace_is_exactly_the_listed_code_points() -> None:
    found = {cp for cp in range(0x110000) if chr(cp).isspace()}
    splitting = {
        cp
        for cp in range(0x110000)
        if " a" + chr(cp) + "b" != "" and len((" a" + chr(cp) + "b").split()) == 2
    }
    assert found == WHITESPACE
    assert splitting == WHITESPACE


def test_splitlines_breaks_at_exactly_the_listed_code_points() -> None:
    broken = {cp for cp in range(0x110000) if len(("x" + chr(cp) + "y").splitlines()) == 2}
    assert broken == LINE_BREAKS


def test_splitlines_edge_cases() -> None:
    assert "\r\r\n\n".splitlines() == ["", "", ""]
    assert "".splitlines() == []
    assert "x\u2027y\x1fz".splitlines() == ["x\u2027y\x1fz"]
    assert "x\u2027y".splitlines() == ["x\u2027y"]


def test_json_response_is_compact_and_keeps_order() -> None:
    value = {"b": 1, "a": "café \U0001f680", "c": [1.5, 1e16, 0.1]}
    expected = '{"b":1,"a":"café \U0001f680","c":[1.5,1e+16,0.1]}'
    assert JSONResponse(value).body == expected.encode()


def test_path_glob_answers_the_previous_golden(tmp_path: Path) -> None:
    cases = json.loads((GOLDEN / "repository" / "glob.json").read_text(encoding="utf-8"))
    golden = json.loads((GOLDEN / "repository" / "glob.golden.json").read_text(encoding="utf-8"))
    for name in cases["files"]:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("", encoding="utf-8")
    for name in cases["dirs"]:
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    got = {}
    for pattern in cases["patterns"]:
        found = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.glob(pattern))
        got[pattern] = found
    assert got == golden


def test_fnmatchcase_is_case_sensitive_and_linear_on_many_stars() -> None:
    assert fnmatch.fnmatchcase("a.rs", "*.rs")
    assert not fnmatch.fnmatchcase("A.rs", "a.rs")
    assert fnmatch.fnmatchcase("a/b/c.rs", "*.rs")
    assert not fnmatch.fnmatchcase("a" * 200 + "b", "*a" * 30 + "c")
    many = "*a" * 30 + "c"
    assert growth(lambda n: fnmatch.fnmatchcase("a" * n + "b", many), 200) < LINEAR_BOUND


def test_random_seed_one_is_the_documented_value() -> None:
    assert random.Random(1).random() == 0.13436424411240122  # noqa: S311
    rng = random.Random(1)  # noqa: S311
    assert all(rng.randrange(n) < n for n in (1, 2, 2**32))


def test_the_old_refusal_forms_come_from_builtins() -> None:
    assert shlex.quote("it's") == "'it'\"'\"'s'"
    assert f"{8192:,}" == "8,192"
    assert repr(1e16) == "1e+16"


@pytest.mark.parametrize("pattern", ["*.rs", "src/*"])
def test_fnmatch_star_crosses_slashes(pattern: str) -> None:
    assert fnmatch.fnmatchcase("src/a/b.rs", pattern)
