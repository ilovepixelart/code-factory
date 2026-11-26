"""Links among tickets: blockers that stand, what a ticket blocks, children and how many landed."""

from board_values import ticket
from code_factory.board.rules.links import Relations
from code_factory.tickets.models import Ticket

STAGES = {"CF-1": "spec", "CF-2": "merged", "CF-3": "released", "CF-4": "build"}


def relations(*tickets: Ticket) -> Relations:
    return Relations(tickets, STAGES)


def test_a_blocker_that_has_not_landed_is_open() -> None:
    waiting = ticket("CF-5", blocked_by=["CF-1", "CF-4"])
    assert relations(waiting, ticket("CF-1"), ticket("CF-4")).open_blockers(waiting) == [
        "CF-1",
        "CF-4",
    ]


def test_a_merged_or_released_blocker_no_longer_blocks() -> None:
    waiting = ticket("CF-5", blocked_by=["CF-2", "CF-3"])
    assert relations(waiting, ticket("CF-2"), ticket("CF-3")).open_blockers(waiting) == []


def test_a_blocker_that_is_not_a_ticket_is_not_listed() -> None:
    waiting = ticket("CF-5", blocked_by=["CF-99"])
    assert relations(waiting).open_blockers(waiting) == []


def test_the_page_link_names_blocks_parent_and_children() -> None:
    parent = ticket("CF-1")
    kid_done = ticket("CF-2", parent="CF-1")
    kid_released = ticket("CF-3", parent="CF-1")
    kid_open = ticket("CF-4", parent="CF-1", blocked_by=["CF-1"])
    assert relations(parent, kid_done, kid_released, kid_open).link(parent) == {
        "open_blockers": [],
        "blocks": ["CF-4"],
        "parent": "",
        "children": 3,
        "children_done": 2,
        "child_ids": ["CF-2", "CF-3", "CF-4"],
    }


def test_a_child_names_its_parent() -> None:
    kid = ticket("CF-4", parent="CF-1")
    assert relations(ticket("CF-1"), kid).link(kid)["parent"] == "CF-1"
