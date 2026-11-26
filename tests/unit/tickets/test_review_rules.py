"""A review's rules, judged without a database: the verdict agrees with the findings, a rule name
is plain (lower-case words joined by `-`, at most 40 characters), severity gives the class."""

import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.tickets.models import Finding, Review
from code_factory.tickets.rules import check_review, finding_class, render_review

BLOCKER = Finding(severity="blocker", text="The title is not saved", requirement_id="CF-7-R1")
NIT = Finding(severity="nit", text="A long line", path="src/a.py", line=12, rule="line-length")


@pytest.mark.parametrize(
    ("review", "problem"),
    [
        (Review(verdict="changes", summary="s"), "a changes verdict needs at least one finding"),
        (Review(verdict="pass", summary="s", findings=[NIT]), "a pass verdict has no findings"),
        (
            Review(
                verdict="changes",
                summary="s",
                findings=[NIT.model_copy(update={"rule": "Bad_Rule"})],
            ),
            "'Bad_Rule' is not a rule name",
        ),
        (
            Review(
                verdict="changes", summary="s", findings=[NIT.model_copy(update={"rule": "a" * 41})]
            ),
            "is not a rule name",
        ),
        (
            Review(verdict="changes", summary="s", findings=[NIT.model_copy(update={"text": " "})]),
            "a finding needs text",
        ),
    ],
)
def test_a_review_that_contradicts_itself_is_refused(review: Review, problem: str) -> None:
    with pytest.raises(BadRequestError, match=problem):
        check_review(review)


def test_a_consistent_review_is_taken() -> None:
    check_review(Review(verdict="pass", summary="All requirements are met."))
    check_review(Review(verdict="changes", summary="One gap.", findings=[BLOCKER, NIT]))


@pytest.mark.parametrize(
    ("severity", "kind"),
    [("blocker", "important"), ("major", "important"), ("minor", "nit"), ("nit", "nit")],
)
def test_severity_gives_the_class(severity: str, kind: str) -> None:
    assert finding_class(severity) == kind


def test_the_review_document_lists_the_verdict_and_each_finding() -> None:
    review = Review(verdict="changes", summary="One gap.", findings=[BLOCKER, NIT])
    assert render_review(review, ["F1", "F2"]) == (
        "# Review\n"
        "\n"
        "Verdict: changes\n"
        "\n"
        "One gap.\n"
        "\n"
        "## Findings\n"
        "\n"
        "- F1 [blocker] CF-7-R1: The title is not saved\n"
        "- F2 [nit] src/a.py:12: A long line [rule: line-length]\n"
    )


def test_a_passing_review_document_has_no_findings_section() -> None:
    review = Review(verdict="pass", summary="All requirements are met.")
    assert render_review(review, []) == "# Review\n\nVerdict: pass\n\nAll requirements are met.\n"
