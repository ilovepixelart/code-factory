"""Stage names, the column a checklist puts a ticket in, and why a move is refused. Expected values
come from the previous implementation's stage, move and board rule tests and the refusals of its
four repository goldens, ids rewritten to CF."""

import pytest

from code_factory.stages.models import EvidenceItem
from code_factory.stages.rules import (
    board_index,
    card_hold,
    declared_for_move,
    effective_stage,
    hold_line,
    is_done,
    is_landed,
    move_refusal,
    refusals,
    reviewable,
    stage_index,
    stage_label,
    stage_of,
    work_done,
)
from stage_values import checklist

URL = "https://github.com/o/r/pull/1"


def with_detail(
    items: list[EvidenceItem], stage: str, detail: str, *, present: bool | None = None
) -> list[EvidenceItem]:
    changes: dict[str, object] = {"detail": detail}
    if present is not None:
        changes["present"] = present
    return [i.model_copy(update=changes) if i.stage == stage else i for i in items]


def test_the_board_has_four_columns_in_process_order() -> None:
    assert [stage_label(s) for s in ("spec", "build", "review", "merged")] == [
        "Spec",
        "Build",
        "Review",
        "Merged",
    ]
    assert stage_index("review") == 2
    assert stage_index("None") is None
    assert board_index("merged") == 3
    assert board_index("unknown") == 4


def test_released_and_an_unknown_name_are_labelled_released() -> None:
    assert (stage_label("released"), stage_label("elsewhere")) == ("Released", "Released")


def test_work_is_done_from_review_on_and_never_for_an_unknown_name() -> None:
    assert is_done("review")
    assert is_done("merged")
    assert is_done("released")
    assert not is_done("build")
    assert not is_done("unknown")


@pytest.mark.parametrize(
    ("name", "landed"),
    [
        ("spec", False),
        ("build", False),
        ("review", False),
        ("merged", True),
        ("released", True),
        ("", False),
    ],
)
def test_merged_and_released_are_the_landed_stages(name: str, landed: bool) -> None:
    assert is_landed(name) is landed


def test_an_optional_stage_without_evidence_is_skipped() -> None:
    assert stage_of(checklist(spec=True)) == "build"


def test_the_first_absent_required_work_stage_is_the_column_and_build_is_the_floor() -> None:
    assert stage_of(checklist()) == "spec"
    assert stage_of(checklist(spec=True, build=True)) == "build"


def test_review_merged_and_released_outrank_the_chain() -> None:
    assert stage_of(checklist(spec=True, build=True, review=True)) == "review"
    assert stage_of(checklist(spec=True, build=True, review=True, merged=True)) == "merged"
    released = checklist()
    released[4] = released[4].model_copy(update={"present": True})
    assert stage_of(released) == "released"


def test_stage_of_does_not_change_when_the_released_item_is_missing() -> None:
    items = checklist(spec=True, build=True)

    assert stage_of(items[:4]) == stage_of(items)


def test_a_declared_stage_wins_over_the_derived_one() -> None:
    assert effective_stage("review", "spec") == "review"
    assert effective_stage("", "spec") == "spec"


def test_work_is_done_when_spec_and_build_are_each_present_or_not_required() -> None:
    assert work_done(checklist(spec=True, build=True))
    assert not work_done(checklist(spec=True))
    optional = [
        EvidenceItem(stage="spec", required=False, present=False, detail="x"),
        EvidenceItem(stage="build", required=True, present=True, detail="y"),
    ]
    assert work_done(optional)


def test_a_ticket_is_reviewable_when_its_work_is_done_and_it_is_not_yet_in_review() -> None:
    built = checklist(spec=True, build=True)

    assert reviewable(built, "build")
    assert not reviewable(built, "review")
    assert not reviewable(built, "released")
    assert not reviewable(checklist(spec=True), "build")


def test_the_hold_is_the_first_required_item_that_is_absent() -> None:
    assert hold_line(checklist(spec=True)) == "needs build: build item"
    assert hold_line(checklist()) == "needs spec: spec item"
    assert hold_line(checklist(spec=True, build=True, review=True, merged=True)) == ""


def test_the_card_hold_repeats_the_detail_and_is_none_for_a_landed_stage() -> None:
    items = checklist(spec=True)

    assert card_hold(items, "build") == {
        "stage": "build",
        "detail": "build item",
        "summary": "build item",
    }
    assert card_hold(items, "merged") is None
    assert card_hold(items, "released") is None


def test_a_card_moves_one_earned_column_at_a_time() -> None:
    unwritten = with_detail(checklist(), "spec", ".tickets/CF-1/spec.md")
    written = with_detail(checklist(spec=True), "spec", ".tickets/CF-1/spec.md")

    assert move_refusal("CF-1", "spec", written, "build") == ""
    assert (
        move_refusal("CF-1", "spec", unwritten, "build")
        == "CF-1 needs .tickets/CF-1/spec.md before Build"
    )
    assert (
        move_refusal("CF-1", "spec", written, "review")
        == "CF-1 moves one column at a time: Build is next"
    )


def test_a_move_to_the_same_or_an_earlier_column_or_an_unknown_one_is_never_refused() -> None:
    items = checklist(spec=True)

    assert move_refusal("CF-1", "build", items, "build") == ""
    assert move_refusal("CF-1", "build", items, "spec") == ""
    assert move_refusal("CF-1", "spec", items, "nowhere") == ""
    assert move_refusal("CF-1", "nowhere", items, "build") == ""


def test_a_card_in_build_with_no_commit_may_not_go_to_review_or_merged() -> None:
    items = with_detail(checklist(spec=True), "build", "a commit on feat/CF-2")

    assert (
        move_refusal("CF-2", "build", items, "review")
        == "CF-2 needs a commit on feat/CF-2 before Review"
    )
    assert (
        move_refusal("CF-2", "build", items, "merged")
        == "CF-2 moves one column at a time: Review is next"
    )


def test_a_card_with_its_commit_is_told_it_needs_a_pull_request_before_review() -> None:
    pushed = "a pull request for feat/CF-2"
    items = with_detail(checklist(spec=True, build=True), "build", "a commit on feat/CF-2")
    unpushed = with_detail(items, "review", "a push of feat/CF-2 and a pull request")

    assert (
        move_refusal("CF-2", "build", with_detail(items, "review", pushed), "review")
        == "CF-2 needs a pull request for feat/CF-2 before Review"
    )
    assert (
        move_refusal("CF-2", "build", unpushed, "review")
        == "CF-2 needs a push of feat/CF-2 and a pull request before Review"
    )


def test_a_card_without_a_branch_is_told_how_to_get_one() -> None:
    items = with_detail(checklist(), "spec", "a branch")

    assert (
        move_refusal("CF-10", "spec", items, "build") == "CF-10 needs a branch before Build: "
        "start an agent on it, or run code-factory start CF-10"
    )


def test_a_move_to_the_column_the_evidence_already_reached_is_allowed() -> None:
    items = checklist(spec=True, build=True, review=True)

    assert move_refusal("CF-1", "build", items, "review") == ""


def test_a_card_whose_checklist_says_released_may_move_forward() -> None:
    items = checklist(spec=True)
    items[4] = items[4].model_copy(update={"present": True})

    assert move_refusal("CF-1", "build", items, "review") == ""


def test_the_refusals_have_one_sentence_per_stage_as_the_delivery_golden_has_them() -> None:
    items = with_detail(checklist(spec=True, build=True, review=True), "review", URL)

    assert refusals("CF-1", "review", items) == {
        "spec": "",
        "build": "",
        "review": "",
        "merged": f"CF-1 needs {URL} before Merged",
    }


def test_nothing_declared_and_dropped_on_the_derived_column_clears_the_pin() -> None:
    assert declared_for_move("", "build", "build") == ""


def test_a_drop_on_another_column_or_with_a_pin_declares_the_target() -> None:
    assert declared_for_move("", "build", "spec") == "spec"
    assert declared_for_move("review", "build", "build") == "build"
