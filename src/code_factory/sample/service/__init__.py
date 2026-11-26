"""Preparing a schema and loading a sample into it."""

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

from code_factory.auth.service import AuthService
from code_factory.memory.models import NewMemory
from code_factory.memory.service import MemoryService
from code_factory.platform.config import Settings, parse_database_url
from code_factory.platform.db import create_schema, drop_schema
from code_factory.platform.db.migrate import upgrade
from code_factory.platform.errors import BadRequestError
from code_factory.sample import rules
from code_factory.sample.models import BOARD_DOCUMENTS, BOARD_MEMORY, BOARD_TICKETS
from code_factory.sample.service.demo import DemoDeps, DemoLoader, demo_root, load_time
from code_factory.tickets.models import DocumentName, DocumentWrite, NewTicket
from code_factory.tickets.service import DocumentService, TicketService

OWNER_LABEL = "owner"
SESSION_DAYS = 365
SAMPLE_AUTHOR = "sample"
_FACTS = ("branch", "merged", "archived")


def check_target(settings: Settings) -> None:
    """Refuse a settings target that is not a test database in a schema of its own."""
    url = parse_database_url(settings.database_url.get_secret_value())
    rules.check_target(url.host, url.database, dict(url.query), settings.db_schema)


async def prepare(settings: Settings) -> None:
    """Create the schema and migrate it to head."""
    check_target(settings)
    await create_schema(settings)
    # Alembic starts its own event loop, so it runs in a thread.
    await asyncio.to_thread(upgrade)


async def drop(settings: Settings) -> None:
    """Drop the schema with everything in it."""
    check_target(settings)
    await drop_schema(settings)


class SampleService:
    """Loads a sample into the schema the process is configured for.

    `owner_sessions` is an `AuthService` whose entropy is fixed, so the owner's session value is
    the same in every sample. `demo` is what the `demo` sample writes through, and the state folder
    its repositories and transcripts go in.
    """

    def __init__(
        self,
        owner_sessions: AuthService,
        tickets: TicketService,
        documents: DocumentService,
        memory: MemoryService,
        demo: tuple[DemoDeps, Path],
    ) -> None:
        self._owner_sessions = owner_sessions
        self._tickets = tickets
        self._documents = documents
        self._memory = memory
        self._demo = demo

    async def load(self, name: str) -> dict[str, str]:
        """Fill an empty prepared schema with the sample `name`; the id of each ticket by title."""
        rules.check_sample(name)
        if await self._owner_sessions.list_tokens(include_ended=True):
            msg = (
                "the schema already holds a sample; run sample-drop, then sample-prepare, "
                "to start from an empty one"
            )
            raise BadRequestError(msg)
        nonce = await self._owner_sessions.issue_sign_in_nonce(OWNER_LABEL)
        await self._owner_sessions.redeem_sign_in_nonce(
            nonce.token.get_secret_value(), lifetime=timedelta(days=SESSION_DAYS)
        )
        if name == "demo":
            return await self._load_demo()
        return await self._load_board() if name == "board" else {}

    async def _load_demo(self) -> dict[str, str]:
        deps, state_dir = self._demo
        return await DemoLoader(deps, demo_root(state_dir), load_time()).load()

    async def _load_board(self) -> dict[str, str]:
        ids: dict[str, str] = {}
        for spec in BOARD_TICKETS:
            fields = {k: v for k, v in spec.items() if k not in _FACTS}
            for link in ("parent", "blocked_by"):
                if link in fields:
                    named = fields[link]
                    fields[link] = ids[named] if isinstance(named, str) else [ids[n] for n in named]
            ticket = await self._tickets.create(NewTicket.model_validate(fields), by=SAMPLE_AUTHOR)
            ids[ticket.title] = ticket.id
            await self._set_facts(ticket.id, spec)
        for title, documents in BOARD_DOCUMENTS.items():
            for document, text in documents.items():
                write = DocumentWrite(content=text)
                await self._documents.write_document(
                    ids[title], DocumentName(document), write, by=SAMPLE_AUTHOR
                )
        for entry in BOARD_MEMORY:
            new = NewMemory.model_validate({**entry, "repository": "sample"})
            await self._memory.add(new, by=SAMPLE_AUTHOR)
        return ids

    async def _set_facts(self, ticket: str, spec: dict[str, Any]) -> None:
        if "branch" in spec:
            await self._tickets.set_branch(ticket, spec["branch"], by=SAMPLE_AUTHOR)
        if spec.get("merged"):
            await self._tickets.set_merged(ticket, True, by=SAMPLE_AUTHOR)
        if spec.get("archived"):
            await self._tickets.archive(ticket, by=SAMPLE_AUTHOR)
