"""The diff reader against the previous implementation's 13 cases, exactly."""

import json
from pathlib import Path

from code_factory.git.rules.diffs import parse_diff

GOLDEN = Path(__file__).parents[2] / "support/golden/formats/diff"


def test_parse_diff_equals_every_golden_case() -> None:
    cases = json.loads((GOLDEN / "cases.json").read_text())
    expected = json.loads((GOLDEN / "cases.golden.json").read_text())
    assert len(cases) == len(expected) == 13
    for text, want in zip(cases, expected, strict=True):
        assert parse_diff(text, 400).model_dump() == want


def _added(count: int) -> str:
    body = "".join(f"+line {n}\n" for n in range(1, count + 1))
    return f"--- /dev/null\n+++ b/f.txt\n@@ -0,0 +1,{count} @@\n{body}"


def test_exactly_the_limit_is_not_cut_and_one_more_is() -> None:
    assert not parse_diff(_added(400)).cut
    cut = parse_diff(_added(401))
    assert cut.cut
    assert len(cut.files[0].lines) == 400


def test_a_dashed_line_inside_a_hunk_is_content_not_a_header() -> None:
    text = "--- a/d\n+++ b/d\n@@ -1,2 +1,2 @@\n--- not a header\n+++ looks like a header\n"
    lines = parse_diff(text).files[0].lines
    assert [(line.kind, line.text) for line in lines] == [
        ("removed", "-- not a header"),
        ("added", "++ looks like a header"),
    ]
