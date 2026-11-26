"""Which guarantees a runtime lacks: the live answer of the previous implementation for the two
runtimes that remain, its ticket ids removed (`tests/golden/agents/gaps.json`)."""

import json
from pathlib import Path

from code_factory.agents.models.constants import RUNTIMES
from code_factory.agents.rules.gaps import gaps_of

GOLDEN = Path(__file__).parent.parent / "golden" / "agents" / "gaps.json"


def test_each_runtime_lacks_what_the_live_answer_said_it_lacked() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert {runtime: gaps_of(runtime) for runtime in RUNTIMES} == golden


def test_an_unknown_runtime_lacks_nothing() -> None:
    assert gaps_of("pi") == []


def test_no_gap_text_names_a_ticket() -> None:
    assert "CF-" not in json.dumps([gaps_of(runtime) for runtime in RUNTIMES])
