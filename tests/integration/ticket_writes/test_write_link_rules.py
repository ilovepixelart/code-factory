"""Link checks and link changes (R links.rs, G[15] to G[17])."""

import pytest

from code_factory.ticket_writes.models import LinkChange
from code_factory.ticket_writes.rules import check_links, link_change
from write_values import core, graph


def test_a_ticket_cannot_name_itself() -> None:
    assert check_links("CF-2", {"blocked_by": ["CF-2"]}, {}, graph(1, 2)) == (
        "CF-2 cannot link to itself"
    )


def test_a_link_to_a_ticket_that_is_not_there_is_refused() -> None:
    assert check_links("CF-2", {"blocked_by": ["CF-9"]}, {}, graph(1, 2)) == "no ticket CF-9"


def test_a_parent_whose_chain_leads_back_is_a_loop() -> None:
    # CF-3 is a child of CF-1; making CF-3 the parent of CF-1 closes the circle.
    assert check_links("CF-1", {"parent": ["CF-3"]}, {}, graph(1, 3, parents={3: 1})) == (
        "parent CF-3 would make a loop"
    )


def test_a_parent_two_steps_up_is_a_loop_too() -> None:
    chain = graph(1, 2, 3, parents={3: 2, 2: 1})
    assert check_links("CF-1", {"parent": ["CF-3"]}, {}, chain) == "parent CF-3 would make a loop"


def test_a_parent_outside_the_ticket_s_own_tree_is_fine() -> None:
    assert check_links("CF-1", {"parent": ["CF-2"]}, {}, graph(1, 2, 3, parents={3: 2})) is None


def test_an_old_link_to_a_missing_ticket_does_not_freeze_the_card() -> None:
    current = {"blocked_by": ["CF-9"]}
    assert check_links("CF-2", {"blocked_by": ["CF-9", "CF-1"]}, current, graph(1, 2)) is None


def test_an_old_link_is_only_exempt_while_unchanged() -> None:
    assert check_links("CF-2", {"parent": ["CF-9"]}, {"parent": ["CF-8"]}, graph(1, 2)) == (
        "no ticket CF-9"
    )


def test_a_new_ticket_has_no_id_to_link_to_itself_with() -> None:
    assert check_links(None, {"parent": ["CF-1"], "blocked_by": ["CF-2"]}, {}, graph(1, 2)) is None
    assert check_links(None, {"caused_by": ["CF-9"]}, {}, graph(1)) == "no ticket CF-9"


@pytest.mark.parametrize(
    ("kind", "holder", "field", "value"),
    [
        ("parent", "CF-1", "parent", "CF-3"),
        ("child", "CF-3", "parent", "CF-1"),
        ("blocked_by", "CF-1", "blocked_by", "CF-3"),
        ("blocks", "CF-3", "blocked_by", "CF-1"),
    ],
)
def test_each_kind_adds_to_the_ticket_that_holds_the_link(
    kind: str, holder: str, field: str, value: str
) -> None:
    own, other = core(1), core(3)
    assert link_change(own, other, kind, "CF-3", add=True) == LinkChange(
        holder=holder, field=field, value=value
    )


@pytest.mark.parametrize(
    ("kind", "own", "other", "holder", "field"),
    [
        ("parent", {"parent": "CF-3"}, {}, "CF-1", "parent"),
        ("child", {}, {"parent": "CF-1"}, "CF-3", "parent"),
        ("blocked_by", {"blocked_by": ["CF-3"]}, {}, "CF-1", "blocked_by"),
        ("blocks", {}, {"blocked_by": ["CF-1"]}, "CF-3", "blocked_by"),
    ],
)
def test_each_kind_removes_back_to_empty(
    kind: str, own: dict[str, object], other: dict[str, object], holder: str, field: str
) -> None:
    change = link_change(core(1, **own), core(3, **other), kind, "CF-3", add=False)
    assert change == LinkChange(holder=holder, field=field, value="")


def test_blockers_are_added_to_the_ones_held_and_removed_singly() -> None:
    own = core(1, blocked_by=["CF-2", "CF-3"])
    assert link_change(own, core(4), "blocked_by", "CF-4", add=True) == LinkChange(
        holder="CF-1", field="blocked_by", value="CF-2, CF-3, CF-4"
    )
    assert link_change(own, core(3), "blocked_by", "CF-3", add=False) == LinkChange(
        holder="CF-1", field="blocked_by", value="CF-2"
    )


def test_adding_a_blocker_already_held_changes_nothing() -> None:
    own = core(1, blocked_by=["CF-3"])
    change = link_change(own, core(3), "blocked_by", "CF-3", add=True)
    assert change == LinkChange(holder="CF-1", field="blocked_by", value="CF-3")


@pytest.mark.parametrize("kind", ["parent", "child", "blocked_by", "blocks"])
def test_removing_a_link_that_is_not_there_names_both_tickets(kind: str) -> None:
    assert link_change(core(1), core(3), kind, "CF-3", add=False) == (
        "CF-3 is not linked to CF-1 that way"
    )


def test_an_unknown_kind_is_refused_before_anything_else() -> None:
    assert link_change(core(1), None, "sibling", "CF-3", add=True) == "unknown link kind sibling"


@pytest.mark.parametrize("kind", ["child", "blocks"])
def test_the_other_ticket_must_exist_when_it_holds_the_link(kind: str) -> None:
    assert link_change(core(1), None, kind, "CF-9", add=True) == "no ticket CF-9"


@pytest.mark.parametrize("kind", ["parent", "blocked_by"])
def test_a_missing_target_is_left_to_the_link_check_when_the_ticket_holds_the_link(
    kind: str,
) -> None:
    change = link_change(core(1), None, kind, "CF-9", add=True)
    assert change == LinkChange(holder="CF-1", field=kind, value="CF-9")
