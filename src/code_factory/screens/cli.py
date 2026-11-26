"""`code-factory shoot <repository> <ticket>`: capture a ticket's pages from the running board."""

import argparse
import sys
from datetime import timedelta

import httpx

from code_factory.auth.service import AuthService
from code_factory.platform.config import Settings, load_settings
from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.screens import adapters
from code_factory.screens.rules import images_of, page_refusal, pages_of
from code_factory.screens.service import ScreensService
from code_factory.tickets.service import TicketService

SESSION = timedelta(minutes=5)
BY = "owner:shoot"


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repository", help="the tracked repository the ticket is in")
    parser.add_argument("ticket", help="the ticket, for example CF-12")
    parser.add_argument(
        "--before",
        action="store_true",
        help="capture the pages as the default branch shows them, while the board runs it",
    )


async def _board_answers(settings: Settings) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            await client.get(f"{settings.base_url}/api/health")
    except httpx.HTTPError:
        msg = f"no board answers at {settings.base_url}; start it with code-factory serve"
        raise UnavailableError(msg) from None


async def _shoot(args: argparse.Namespace, services: Services) -> int:
    settings = load_settings()
    ticket = await services.get(TicketService).locate(args.repository, args.ticket)
    found = await services.get(TicketService).get(ticket.id)
    pages = pages_of(found.pages or "", args.repository, ticket.id)
    if (
        refusal := next((r for p in pages if (r := page_refusal(p)) is not None), None)
    ) is not None:
        raise BadRequestError(refusal)
    root = await services.get(RepositoryService).get(args.repository)
    tree = await adapters.tree_of(root, "HEAD" if args.before else found.branch or "HEAD")
    await _board_answers(settings)
    screens = services.get(ScreensService)
    folder = screens.folder_of(args.repository, ticket.id, tree)
    folder.mkdir(parents=True, exist_ok=True)
    auth = services.get(AuthService)
    nonce = await auth.issue_sign_in_nonce("shoot")
    session = await auth.redeem_sign_in_nonce(nonce.token.get_secret_value(), lifetime=SESSION)
    if session is None:
        msg = "the capture could not sign in"
        raise UnavailableError(msg)
    try:
        await adapters.capture(settings.base_url, folder, pages, session.token)
    finally:
        await auth.revoke(session.id)
    images = images_of(pages)
    if args.before:
        await screens.record_before(ticket.id, tree, images, by=BY)
    else:
        await screens.record(ticket.id, tree, images, by=BY)
    for image in images:
        sys.stdout.write(f"wrote {folder / image}\n")
    return 0


shoot_command = Command(
    "shoot", "capture a ticket's pages from the running board, light and dark",
    configure=_configure, run_async=_shoot,
)  # fmt: skip
