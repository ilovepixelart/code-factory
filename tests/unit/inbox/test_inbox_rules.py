"""The inbox page rules against the recorded golden page and hand cases."""

import json
from pathlib import Path

from code_factory.inbox.models import SECTIONS, Item, TicketRef
from code_factory.inbox.rules import (
    build_page,
    describe,
    hide_covered,
    oldest_first,
    permission_item,
)

GOLDEN = json.loads(
    (Path(__file__).parents[2] / "support/golden/formats/metrics/inbox.golden.json").read_text()
)


def test_the_page_of_the_golden_items_is_the_golden_page() -> None:
    sections = {name: [Item.model_validate(i) for i in GOLDEN[name]] for name in SECTIONS}
    assert build_page(sections, None) == GOLDEN


def test_each_kind_of_item_has_its_sentence() -> None:
    ticket = TicketRef(repository="r", id="CF-3", title="t")
    assert describe(Item(ticket=ticket, kind="merge")) == "CF-3 is ready to merge"
    assert describe(Item(ticket=ticket, kind="merge", note="review")) == "CF-3: review before merge"
    assert describe(Item(ticket=ticket, kind="failing")) == "CF-3: CI failed on its pull request"
    assert describe(Item(ticket=ticket, reason="agent failed (exit 1)")) == (
        "CF-3 stopped: agent failed (exit 1)"
    )
    main = {"repository": "r", "commit": "abcdef123", "step": "lint"}
    assert describe(Item(main=main)) == "r: main fails lint at abcdef1"


def test_a_question_covers_a_stopped_item_of_its_ticket() -> None:
    ticket = TicketRef(repository="r", id="CF-3", title="t")
    other = TicketRef(repository="r", id="CF-4", title="u")
    sections = {
        "questions": [Item(ticket=ticket, question={"text": "?"})],
        "stopped": [Item(ticket=ticket, reason="x"), Item(ticket=other, reason="y")],
    }
    assert [i.ticket.id for i in hide_covered(sections)["stopped"] if i.ticket] == ["CF-4"]


def test_undated_items_lead_then_the_oldest() -> None:
    items = [Item(since=3.0, reason="c"), Item(reason="u"), Item(since=1.0, reason="a")]
    assert [i.reason for i in oldest_first(items)] == ["u", "a", "c"]
    assert [i.reason for i in oldest_first(items, newest=True)] == ["u", "c", "a"]


def test_a_permission_note_falls_back_to_its_tally() -> None:
    request = {"tool": "Bash", "summary": "npm test --watch", "note": ""}
    assert permission_item(request, (2, 3)) == {
        "reason": "Bash npm test --watch", "note": "allowed 2 of 3 times before"
    }  # fmt: skip
    assert permission_item(request | {"note": "own"}, (2, 3))["note"] == "own"
