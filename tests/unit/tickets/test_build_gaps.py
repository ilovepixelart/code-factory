"""What a ticket's documents lack before Build may start (docs/agents.md, the pipeline)."""

import pytest

from code_factory.tickets.rules import build_gaps

REQUIREMENTS = (
    "# R\n\n## Requirements\n\n| ID | Requirement | Named check |\n|---|---|---|\n"
    "| R1 | Codes are unique | test_unique |\n"
)
SPEC = "# Spec\n\nDesign.\n\n## Blast radius\n\n- payments/codes.py: a new column\n"


def test_documents_with_a_named_check_on_every_row_and_a_blast_radius_are_ready() -> None:
    assert build_gaps(REQUIREMENTS, SPEC) == []


@pytest.mark.parametrize(
    ("spec", "gap"),
    [
        ("# Spec\n\nDesign.\n", "spec has no ## Blast radius section"),
        (
            "# Spec\n\n## Blast radius\n\n\n## Out of scope\n\n- x\n",
            "spec's ## Blast radius section is empty",
        ),
        ("", "spec has no ## Blast radius section"),
    ],
)
def test_a_spec_without_a_blast_radius_is_not_ready(spec: str, gap: str) -> None:
    assert build_gaps(REQUIREMENTS, spec) == [gap]


def test_missing_requirements_and_an_unnamed_check_are_named() -> None:
    unnamed = REQUIREMENTS.replace("test_unique", "")
    assert build_gaps("", SPEC) == ["requirements has no ## Requirements table"]
    assert build_gaps(unnamed, SPEC) == ["requirements row 1 (R1) has no named check"]
