"""Which capture waits, and which names may reach the captures folder."""

import re
from collections.abc import Sequence
from typing import Any

from code_factory.screens.models import APPROVED, CAPTURED, CHANGES

# A tree is a git content digest; an image a plain file name the capture recorded.
TREE = re.compile(r"[0-9a-f]{7,64}")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.png")


def waiting(records: Sequence[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    """The data of the latest capture when no answer names its tree; records oldest first."""
    shot = next((data for kind, data in reversed(records) if kind == CAPTURED), None)
    if shot is None:
        return None
    tree = shot.get("tree")
    answered = any(
        kind in {APPROVED, CHANGES} and data.get("tree") == tree for kind, data in records
    )
    return None if answered else shot


def plain_names(tree: str, image: str) -> bool:
    """Whether `tree` and `image` are names a capture can hold, never a path."""
    return TREE.fullmatch(tree) is not None and IMAGE.fullmatch(image) is not None


THEMES = ("light", "dark")
_SECTION = re.compile(r"[A-Za-z0-9_-]+")


def pages_of(declared: str, repository: str, ticket: str) -> list[str]:
    """The pages a capture shows: the ticket's `pages`, comma-separated, else the ticket's own."""
    named = [page.strip() for page in declared.split(",") if page.strip()]
    return named or [f"/tickets/{repository}/{ticket}"]


def page_refusal(page: str) -> str | None:
    """Why `page` cannot be captured: it must be a path on the board, and a `#section` an id."""
    if not page.startswith("/"):
        return f"{page} is not a path on the board: a page starts with /"
    _, mark, section = page.partition("#")
    if mark and _SECTION.fullmatch(section) is None:
        return (
            f"{page} names no section the capture can scroll to: after # comes an element id "
            "of letters, digits, - and _"
        )
    return None


def image_stem(page: str) -> str:
    """A page as a file name: letters and digits, every other run of characters one `-`."""
    stem = re.sub(r"[^A-Za-z0-9]+", "-", page).strip("-")
    return stem or "board"


def images_of(pages: list[str]) -> list[str]:
    """The images a capture of `pages` writes: each page in light, then dark."""
    return [f"{image_stem(page)}-{theme}.png" for page in pages for theme in THEMES]
