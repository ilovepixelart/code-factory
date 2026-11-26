"""Supersession, edits, approval, retirement and merging as rules over entries."""

import pytest

from code_factory.memory.models import MemoryEdit
from code_factory.memory_extras.rules import (
    approved,
    dismissed,
    edited,
    merge_patches,
    plan_supersession,
    retirement,
    superseded,
)
from code_factory.platform.errors import BadRequestError
from memory_extras_values import entry

OLD = "2026-10-01-merge-at-once"
NEW = "2026-11-10-land-through-one-queue"


def test_a_supersession_retires_each_active_entry_it_names_with_its_reason() -> None:
    plan = plan_supersession(NEW, [OLD, "2026-10-02-b"], {OLD, "2026-10-02-b", "x"}, set())
    assert plan == [OLD, "2026-10-02-b"]


def test_an_entry_already_retired_is_skipped() -> None:
    assert plan_supersession(NEW, [OLD], set(), {OLD}) == []


def test_an_entry_cannot_supersede_itself() -> None:
    with pytest.raises(BadRequestError, match=r"^an entry cannot supersede itself$"):
        plan_supersession(NEW, [NEW], {NEW}, set())


def test_a_supersession_of_no_entry_is_refused() -> None:
    with pytest.raises(BadRequestError, match=r"^no entry 2026-01-01-nothing to supersede$"):
        plan_supersession(NEW, ["2026-01-01-nothing"], {OLD}, {"2026-01-02-gone"})


def test_only_an_active_unproposed_entry_supersedes_an_active_one() -> None:
    old = entry(OLD)
    by = entry(NEW, supersedes=[OLD])
    assert superseded([old, by]) == {OLD: NEW}
    assert superseded([old, entry(NEW, supersedes=[OLD], proposed=True)]) == {}
    assert superseded([old, entry(NEW, supersedes=[OLD], retired="done")]) == {}
    assert superseded([entry(OLD, retired="done"), by]) == {}


def test_an_empty_edit_only_marks_the_entry_reviewed() -> None:
    assert edited(entry(), MemoryEdit(), "2026-11-10") == {"reviewed": "2026-11-10"}


def test_an_edit_changes_only_the_named_fields_trimmed_and_marks_reviewed() -> None:
    changed = edited(
        entry(),
        MemoryEdit(statement="  New words \n", why=" because ", supersedes=[" a ", ""]),
        "2026-11-10",
    )
    assert changed == {
        "statement": "New words",
        "why": "because",
        "supersedes": ["a"],
        "reviewed": "2026-11-10",
    }


def test_an_edit_with_a_blank_statement_or_a_bad_scope_is_refused() -> None:
    with pytest.raises(BadRequestError, match=r"^an entry needs a statement$"):
        edited(entry(), MemoryEdit(statement="  "), "2026-11-10")
    with pytest.raises(BadRequestError, match=r"^scope names core"):
        edited(entry(), MemoryEdit(scope="bulid"), "2026-11-10")


def test_an_edit_keeps_the_fields_it_does_not_name_through_the_checks() -> None:
    held = entry(expires="soon")
    with pytest.raises(BadRequestError, match=r"^expires is a date"):
        edited(held, MemoryEdit(why="x"), "2026-11-10")


def test_approving_a_proposal_clears_it_and_marks_it_reviewed() -> None:
    assert approved(entry(proposed=True), "2026-11-10") == {
        "proposed": False,
        "reviewed": "2026-11-10",
    }


def test_approving_or_dismissing_an_entry_that_is_not_a_proposal_is_refused() -> None:
    with pytest.raises(BadRequestError, match=r"^2026-11-10-scoped is not proposed$"):
        approved(entry(), "2026-11-10")
    with pytest.raises(BadRequestError, match=r"^2026-11-10-scoped is not proposed$"):
        dismissed(entry())


def test_dismissing_a_proposal_retires_it_as_dismissed_by_the_owner() -> None:
    assert dismissed(entry(proposed=True)) == {"retired": "dismissed by the owner"}


def test_a_retirement_reason_is_one_non_empty_line() -> None:
    assert retirement(entry(), "  no longer true  ") == "no longer true"
    for reason in ("", "   ", "a\nb"):
        with pytest.raises(BadRequestError, match=r"^say in one line why it no longer applies$"):
            retirement(entry(), reason)


def test_a_retired_entry_cannot_be_retired_again_and_that_is_said_first() -> None:
    with pytest.raises(BadRequestError, match=r"^2026-11-10-scoped is retired already$"):
        retirement(entry(retired="x"), "")


def test_a_merge_retires_the_entry_naming_the_target_and_adds_the_sources_it_lacks() -> None:
    one = entry("2026-10-01-one", "Do it twice", source="chat; CF-1")
    target = entry("2026-10-02-two", "Do it once", source="CF-1; owner")
    patches = merge_patches(one, target)
    assert patches.retired == {
        "retired": 'merged into "Do it once"',
        "merged_into": "2026-10-02-two",
    }
    assert patches.target == {"source": "CF-1; owner; chat"}


def test_a_merge_leaves_the_target_alone_when_it_names_every_source() -> None:
    one = entry("2026-10-01-one", "Do it twice", source="chat")
    target = entry("2026-10-02-two", "Do it once", source="chat; CF-1")
    assert merge_patches(one, target).target is None
