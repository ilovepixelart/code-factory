"""The screens module's public API: `ScreensService`."""

from pathlib import Path
from typing import Any

import anyio

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.screens.models import APPROVED, BEFORE, CAPTURED, CHANGES, KINDS, Capture
from code_factory.screens.rules import plain_names, waiting
from code_factory.tickets.models import NewActivity
from code_factory.tickets.service import ActivityService, TicketService

NONE_WAITS = "no capture of this ticket waits"
NO_CAPTURE = "no such capture"
PAGE = 100


class ScreensService:
    """Records captures and the owner's verdicts on them, and finds their images."""

    def __init__(self, tickets: TicketService, activity: ActivityService, folder: Path) -> None:
        self._tickets = tickets
        self._activity = activity
        self._folder = folder

    async def _records(self, ticket: str) -> list[tuple[str, dict[str, Any]]]:
        page = await self._activity.list_activity(
            ticket, kinds=list(KINDS), limit=PAGE, newest_first=True
        )
        return [(item.kind, item.data) for item in reversed(page.items)]

    async def record(self, ticket: str, tree: str, images: list[str], *, by: str) -> None:
        """Record a capture of `tree` whose images are already in its folder."""
        if not all(plain_names(tree, image) for image in images) or not images:
            msg = "a capture names its tree and at least one .png image by plain name"
            raise BadRequestError(msg)
        record = NewActivity(kind=CAPTURED, data={"tree": tree, "images": images})
        await self._activity.append(ticket, record, by=by)

    async def record_before(self, ticket: str, tree: str, images: list[str], *, by: str) -> None:
        """Record a capture of the default branch's `tree`: the pages before the ticket's change."""
        if not all(plain_names(tree, image) for image in images) or not images:
            msg = "a capture names its tree and at least one .png image by plain name"
            raise BadRequestError(msg)
        record = NewActivity(kind=BEFORE, data={"tree": tree, "images": images})
        await self._activity.append(ticket, record, by=by)

    async def waiting(self) -> list[Capture]:
        """Every live ticket's capture that waits on the owner."""
        found = []
        for ticket in await self._tickets.list():
            page = await self._activity.list_activity(
                ticket.id, kinds=list(KINDS), limit=PAGE, newest_first=True
            )
            records = [(item.kind, item.data) for item in reversed(page.items)]
            shot = waiting(records)
            if shot is not None:
                at = next(i.at for i in page.items if i.kind == CAPTURED)
                images = tuple(str(name) for name in shot.get("images", []))
                found.append(
                    Capture(ticket=ticket.id, tree=str(shot["tree"]), images=images, at=at)
                )
        return found

    async def _waiting_tree(self, ticket: str) -> str:
        shot = waiting(await self._records(ticket))
        if shot is None:
            raise ConflictError(NONE_WAITS)
        return str(shot["tree"])

    async def approve(self, ticket: str, *, by: str) -> None:
        """Approve the waiting capture's tree."""
        tree = await self._waiting_tree(ticket)
        await self._activity.append(
            ticket, NewActivity(kind=APPROVED, data={"tree": tree, "by": by}), by=by
        )

    async def send_back(self, ticket: str, reason: str, *, by: str) -> None:
        """Send the waiting capture back with what should change."""
        if not reason.strip():
            msg = "say what should change"
            raise BadRequestError(msg)
        tree = await self._waiting_tree(ticket)
        data = {"tree": tree, "reason": reason.strip()}
        await self._activity.append(ticket, NewActivity(kind=CHANGES, data=data), by=by)

    def folder_of(self, repository: str, ticket: str, tree: str) -> Path:
        """Where a capture's images are kept."""
        return self._folder / repository / ticket / tree

    async def image(self, repository: str, ticket: str, tree: str, image: str) -> Path:
        """The file of an image a recorded capture of `tree` lists; 404 for anything else."""
        if not plain_names(tree, image):
            raise NotFoundError(NO_CAPTURE)
        records = await self._records(ticket)
        listed = any(
            kind == CAPTURED and data.get("tree") == tree and image in data.get("images", [])
            for kind, data in records
        )
        path = self.folder_of(repository, ticket, tree) / image
        if not listed or not await anyio.Path(path).is_file():
            raise NotFoundError(NO_CAPTURE)
        return path
