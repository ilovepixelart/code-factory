"""The checklist a ticket's facts make: every case is a card of the previous delivery and checks
goldens, translated by hand into the facts and the recorded pull request that produced it."""

import pytest

from code_factory.stages.models import BranchFacts, EvidenceItem
from code_factory.stages.rules import derive_evidence
from stage_values import details, shape

URL = "https://github.com/o/r/pull/1"
UNTRACED = (
    "feat/CF-8 has no local or remote branch here, and main holds no pull request merge of it nor,"
    " in its last 1000 commits, a commit starting with CF-8 that landed work"
)
NO_PR = "a pull request for feat/CF-2"


def read(
    branch: str, facts: BranchFacts, opened: str | None = None, release: str | None = None
) -> list[EvidenceItem]:
    return derive_evidence(branch, facts, opened, release)


def test_a_pushed_branch_with_a_commit_and_a_recorded_pull_request_is_in_review() -> None:
    facts = BranchFacts(known=True, local=True, pushed=True, has_commits=True)

    items = read("feat/CF-1", facts, opened=URL)

    assert shape(items) == "PrPrPr-r-o"
    assert details(items) == [
        "a branch",
        "a commit on feat/CF-1",
        URL,
        "a merge into main",
        "a release note naming it",
    ]
    assert [item.stage for item in items] == ["spec", "build", "review", "merged", "released"]


def test_a_pushed_branch_with_no_commit_and_no_pull_request_stays_in_build() -> None:
    facts = BranchFacts(known=True, local=True, pushed=True)

    items = read("feat/CF-2", facts)

    assert shape(items) == "Pr-r-r-r-o"
    assert items[2].detail == NO_PR


def test_a_local_branch_with_commits_is_built_and_names_the_remote_it_waits_for() -> None:
    facts = BranchFacts(known=True, local=True, has_commits=True)

    items = read("feat/CF-7", facts)

    assert shape(items) == "PrPr-r-r-o"
    assert items[2].detail == "a push of feat/CF-7 and a pull request"


def test_a_local_branch_with_no_commit_is_started_but_not_built() -> None:
    items = read("feat/CF-4", BranchFacts(known=True, local=True))

    assert shape(items) == "Pr-r-r-r-o"
    assert items[1].detail == "a commit on feat/CF-4"
    assert items[2].detail == "a push of feat/CF-4 and a pull request"
    assert items[3].detail == "a merge into main"


def test_a_merged_branch_has_every_stage_but_the_release() -> None:
    facts = BranchFacts(known=True, local=True, merged=True)

    items = read("feat/CF-6", facts)

    assert shape(items) == "PrPrPrPr-o"
    assert (items[2].detail, items[3].detail) == ("origin/feat/CF-6", "main")


def test_a_merged_branch_pushed_without_a_pull_request_names_its_remote_branch() -> None:
    facts = BranchFacts(known=True, local=True, pushed=True, has_commits=True, merged=True)

    assert read("feat/CF-6", facts)[2].detail == "origin/feat/CF-6"


def test_a_ticket_with_no_branch_is_at_spec_and_asks_for_one() -> None:
    items = read("", BranchFacts(known=True))

    assert shape(items) == "-r-r-r-r-o"
    assert details(items)[:3] == ["a branch", "a branch", "no branch declared"]


def test_a_release_naming_the_ticket_makes_the_released_item_present_with_its_name() -> None:
    facts = BranchFacts(known=True, merged=True)

    items = read("feat/CF-7", facts, release="0.1.0")

    assert shape(items) == "PrPrPrPrPo"
    assert items[4].detail == "0.1.0"


def test_work_that_landed_untraced_names_why_it_is_not_merged() -> None:
    facts = BranchFacts(known=True, untraced=UNTRACED)

    items = read("feat/CF-8", facts, release="0.1.0")

    assert shape(items) == "-r-r-r-rPo"
    assert items[3].detail == UNTRACED


def test_a_branch_in_a_worktree_is_started_before_it_has_a_ref() -> None:
    items = read("feat/CF-9", BranchFacts(known=True, in_worktree=True))

    assert shape(items) == "Pr-r-r-r-o"


def test_a_pull_request_on_a_branch_that_is_not_pushed_is_not_in_review() -> None:
    facts = BranchFacts(known=True, local=True, has_commits=True, pushed=False)

    items = read("feat/CF-1", facts, opened=URL)

    assert shape(items) == "PrPr-r-r-o"


def test_a_pushed_branch_with_commits_is_built_before_and_after_its_pull_request_opens() -> None:
    facts = BranchFacts(known=True, pushed=True, has_commits=True)

    before = read("feat/CF-1", facts)
    after = read("feat/CF-1", facts, opened=URL)

    assert (before[1].present, after[1].present, after[2].present) == (True, True, True)
    assert before[2].present is False


def test_a_commit_on_an_unstarted_branch_name_does_not_count() -> None:
    facts = BranchFacts(known=True, has_commits=True)

    items = read("feat/CF-3", facts)

    assert shape(items) == "-r-r-r-r-o"


@pytest.mark.parametrize("merged", [True, False])
def test_a_merged_ticket_is_built_even_with_no_commit_of_its_own(merged: bool) -> None:
    facts = BranchFacts(known=True, local=True, merged=merged, has_commits=False)

    assert read("feat/CF-6", facts)[1].present is merged


def test_a_default_branch_other_than_main_is_named_in_the_merged_detail() -> None:
    items = read("feat/CF-1", BranchFacts(known=True, default_branch="trunk"))
    merged = read("feat/CF-1", BranchFacts(known=True, default_branch="trunk", merged=True))

    assert (items[3].detail, merged[3].detail) == ("a merge into trunk", "trunk")
