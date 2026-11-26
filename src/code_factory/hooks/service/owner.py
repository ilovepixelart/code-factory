"""The owner's commands that need no running agent: `open`, `sign-out` and `audit export`."""

from typing import Any

from code_factory.hooks.models import OpenedBoard, OpenerUnavailableError
from code_factory.hooks.rules.audit import export_line
from code_factory.hooks.rules.open_board import board_page, owner_link
from code_factory.hooks.service.base import Collaborators
from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.platform.text import is_iso_date

BAD_PAGE = "the page must be a path on the board, such as /inbox"


class OwnerMixin(Collaborators):
    """Sign the browser in or out, and list who did what."""

    def _base(self, port: int | None) -> str:
        host = self._ports.board.host
        shown = f"[{host}]" if ":" in host else host
        return f"http://{shown}:{port or self._ports.board.port}"

    async def open_board(self, page: str = "/", *, port: int | None = None) -> OpenedBoard:
        """Open the default browser on `page`, signed in with a one-time nonce.

        `BadRequestError` for a page off the board, `UnavailableError` when no board answers or no
        browser opens (the nonce is spent then, so the unused link opens nothing).
        """
        if board_page(page) is None:
            raise BadRequestError(BAD_PAGE)
        base = self._base(port)
        if not await self._ports.probe.up(base):
            msg = f"no board answers at {base}: start code-factory serve first"
            raise UnavailableError(msg)
        nonce = await self._ports.auth.mint()
        try:
            await self._ports.opener.open_url(owner_link(base, nonce, page))
        except (OpenerUnavailableError, OSError) as error:
            await self._ports.auth.spend(nonce)
            msg = f"could not open a browser: {error}; run code-factory sign-in for the link"
            raise UnavailableError(msg) from error
        return OpenedBoard(line=f"opened {base}{page} in the default browser")

    async def sign_out(self) -> int:
        """End every owner session; how many."""
        return await self._ports.auth.end_sessions()

    async def audit_export(self, since: str) -> list[dict[str, Any]]:
        """Who did what on every tracked repository's tickets since the day, oldest first.

        `BadRequestError` for a day that is not `YYYY-MM-DD`. Reads only.
        """
        if not is_iso_date(since):
            msg = f'"{since}" is not a day as YYYY-MM-DD'
            raise BadRequestError(msg)
        lines = [
            line
            for repository, record in await self._ports.tickets.activity()
            if (line := export_line(record, repository, since)) is not None
        ]
        return sorted(lines, key=lambda line: (line["at"], line["repository"], line["ticket"]))
