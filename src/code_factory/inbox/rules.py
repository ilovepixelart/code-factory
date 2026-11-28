"""Pure rules of the inbox: sentences, order, what covers what, and the page."""

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from code_factory.inbox.models import COUNTED, SECTIONS, Item, Sections

COVERING = ("questions", "screens", "mergeable")
COVERED = ("stopped", "failing", "idle")
SUMMARY_CUT = 80


def _id(item: Item) -> str:
    return item.ticket.id if item.ticket else ""


def describe(item: Item) -> str:  # noqa: PLR0911  # one sentence per kind of item
    """The one-line sentence of an item."""
    if item.question is not None:
        return f"{_id(item)} asks: {item.question.get('text', '')}"
    if item.session is not None:
        return f"A session in {PurePosixPath(str(item.session.get('cwd', ''))).name} waits on you"
    if item.main is not None:
        step = f" {item.main['step']}" if item.main.get("step") else ""
        return f"{item.main['repository']}: main fails{step} at {str(item.main['commit'])[:7]}"
    if item.kind == "failing":
        return f"{_id(item)}: {item.note or 'CI failed on its pull request'}"
    if item.kind == "idle":
        return f"{_id(item)} has an idle pull request"
    if item.kind == "stuck":
        return f"{_id(item)}: {item.note}"
    if item.kind == "merge":
        return (
            f"{_id(item)}: review before merge" if item.note else f"{_id(item)} is ready to merge"
        )
    if item.kind == "screens":
        return f"{_id(item)}: screens wait for your approval"
    if item.kind == "permission":
        return f"{_id(item)} asks permission: {item.reason}"
    return f"{_id(item)} stopped: {item.reason}"


def oldest_first(items: list[Item], *, newest: bool = False) -> list[Item]:
    """Items with no `since` first in their order, then by `since`; `newest` reverses the dated."""
    undated = [i for i in items if i.since is None]
    dated = sorted((i for i in items if i.since is not None), key=lambda i: i.since or 0.0)
    return undated + (dated[::-1] if newest else dated)


def hide_covered(sections: Sections) -> Sections:
    """Drop a stopped or failing item whose ticket has a question, screens or merge item."""
    covering = {_id(i) for name in COVERING for i in sections.get(name, []) if i.ticket}
    return {
        name: [i for i in items if not (name in COVERED and i.ticket and _id(i) in covering)]
        for name, items in sections.items()
    }


def permission_item(request: Mapping[str, Any], tally: tuple[int, int] | None) -> dict[str, str]:
    """The reason and note of a permission request."""
    reason = f"{request['tool']} {str(request['summary'])[:SUMMARY_CUT]}"
    note = str(request.get("note") or "")
    if not note and tally is not None and tally[1]:
        note = f"allowed {tally[0]} of {tally[1]} times before"
    return {"reason": reason, "note": note}


def _since(item: Item) -> float:
    return item.since if item.since is not None else float("-inf")


def attention(sections: Sections) -> dict[str, Any]:
    """How many items need an answer and the newest item's sentence."""
    counted = [item for name in COUNTED for item in sections.get(name, [])]
    latest = max(counted, key=_since, default=None)
    return {"count": len(counted), "latest": describe(latest) if latest is not None else ""}


def build_page(sections: Sections, push: dict[str, Any] | None) -> dict[str, Any]:
    """The `/api/inbox` answer: the sections in order, the count, the latest and the next up."""
    ordered = {name: sections.get(name, []) for name in SECTIONS}
    counted = ((name, index, item) for name in COUNTED for index, item in enumerate(ordered[name]))
    next_up = min(counted, key=lambda entry: _since(entry[2]), default=None)
    page: dict[str, Any] = {
        name: [i.model_dump(mode="json") for i in items] for name, items in ordered.items()
    }
    page.update(attention(ordered))
    page["push"] = push
    page["next_up"] = {"section": next_up[0], "index": next_up[1]} if next_up else None
    return page
