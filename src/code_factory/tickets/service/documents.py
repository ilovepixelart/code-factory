"""A ticket's documents: versioned markdown, written whole or appended to, read in pages."""

from collections.abc import Callable
from datetime import datetime

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.tickets.models import (
    Document,
    DocumentInfo,
    DocumentName,
    DocumentPage,
    DocumentWrite,
    DocumentWritten,
    MockFile,
    MockFileInfo,
    Problem,
    WriteMode,
)
from code_factory.tickets.repository import (
    DocumentRepository,
    MockFileRepository,
    TicketRepository,
)
from code_factory.tickets.rules import (
    DOCUMENT_LIMIT,
    build_gaps,
    check_mock,
    mock_type,
    ticket_id,
    ticket_number,
    validate_document,
)
from code_factory.tickets.service.common import not_found, utc_now
from code_factory.tickets.tables import TicketDocumentRow, TicketMockFileRow

_ORDER = list(DocumentName)
_PROBLEMS_SHOWN = 10


def _refusal(problems: list[Problem]) -> BadRequestError:
    said = [f"{p.message} (line {p.line})" if p.line else p.message for p in problems]
    return BadRequestError("; ".join(said[:_PROBLEMS_SHOWN]) + "; fix it and write again")


def _next_body(
    current: TicketDocumentRow | None,
    content: str,
    change: tuple[WriteMode, int | None],
    name: DocumentName,
) -> str:
    """The body a write leaves; `ConflictError` when a replace names the wrong version."""
    mode, base = change
    if mode == "append":
        if current is None or not current.body:
            return content
        joint = "" if current.body.endswith("\n") else "\n"
        return f"{current.body}{joint}{content}"
    if current is None:
        if base is not None:
            msg = f"{name} does not exist yet; write it without base_version"
            raise ConflictError(msg)
        return content
    if base is None:
        msg = f"{name} exists at version {current.version}; read it and write with base_version"
        raise ConflictError(msg)
    if base != current.version:
        msg = (
            f"{name} is at version {current.version}, written from {base}; read it, merge your "
            f"change and write with base_version {current.version}"
        )
        raise ConflictError(msg)
    return content


def _missing(number: int, name: DocumentName) -> NotFoundError:
    return NotFoundError(
        f"{ticket_id(number)} has no {name}; list its documents to see which exist"
    )


def document_index(rows: list[TicketDocumentRow]) -> list[DocumentInfo]:
    """The documents without their text, in the order they are written."""
    found = [
        DocumentInfo(
            name=DocumentName(row.name),
            version=row.version,
            chars=len(row.body),
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
    return sorted(found, key=lambda info: _ORDER.index(info.name))


def _mock_info(row: TicketMockFileRow) -> MockFileInfo:
    return MockFileInfo(
        name=row.name,
        content_type=row.content_type,
        size=len(row.data),
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


class DocumentService:
    """Read and write a ticket's documents."""

    def __init__(self, uow: UnitOfWork, clock: Callable[[], datetime] = utc_now) -> None:
        self._uow = uow
        self._clock = clock

    async def write_document(
        self, ticket: str, name: DocumentName, write: DocumentWrite, *, by: str
    ) -> DocumentWritten:
        """Replace the document (naming the version read, none to create it) or append to it.

        The text it leaves (an append's whole result, not only what it adds) is held to the size
        limit and to `validate_document`, and refused with each problem's line.
        Records a `document` activity with the name and the new version.
        """
        number = ticket_number(ticket)
        if len(write.content) > DOCUMENT_LIMIT:
            msg = f"a document is at most {DOCUMENT_LIMIT} characters; it has {len(write.content)}"
            raise BadRequestError(msg)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number, for_update=True) is None:
                raise not_found(number)
            store = DocumentRepository(session)
            current = await store.find(number, name.value)
            body = _next_body(current, write.content, (write.mode, write.base_version), name)
            if len(body) > DOCUMENT_LIMIT:
                over = len(body) - DOCUMENT_LIMIT
                msg = (
                    f"{name} would be {len(body)} characters, {over} over the limit of "
                    f"{DOCUMENT_LIMIT}; shorten it, or replace it with a shorter whole text"
                )
                raise BadRequestError(msg)
            problems = validate_document(name, body)
            if problems:
                raise _refusal(problems)
            now = self._clock()
            row = current or TicketDocumentRow(ticket_number=number, name=name.value, version=0)
            row.body, row.version, row.updated_by, row.updated_at = body, row.version + 1, by, now
            await store.save(row)
            record = {"name": name.value, "version": row.version}
            await tickets.append_activity(number, (now, "document", by), record)
            return DocumentWritten(name=name, version=row.version)

    async def read_document(
        self, ticket: str, name: DocumentName, offset: int = 0, max_chars: int = 20_000
    ) -> DocumentPage:
        """Up to `max_chars` of the document's text from `offset`."""
        whole = await self.get_document(ticket, name)
        start = max(offset, 0)
        end = start + max(max_chars, 1)
        return DocumentPage(
            name=name,
            version=whole.version,
            text=whole.body[start:end],
            offset=start,
            next_offset=end if end < len(whole.body) else None,
            total_chars=len(whole.body),
            updated_by=whole.updated_by,
            updated_at=whole.updated_at,
        )

    async def build_gaps(self, ticket: str) -> list[str]:
        """What the ticket's requirements and spec lack before Build may start; empty when ready."""
        texts = {}
        for name in (DocumentName.REQUIREMENTS, DocumentName.SPEC):
            try:
                texts[name] = (await self.get_document(ticket, name)).body
            except NotFoundError:
                texts[name] = ""
        return build_gaps(texts[DocumentName.REQUIREMENTS], texts[DocumentName.SPEC])

    async def get_document(self, ticket: str, name: DocumentName) -> Document:
        """The whole document; `NotFoundError` when the ticket has none of that name."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            if await TicketRepository(session).find(number) is None:
                raise not_found(number)
            row = await DocumentRepository(session).find(number, name.value)
        if row is None:
            raise _missing(number, name)
        return Document(
            ticket_id=ticket_id(number),
            name=name,
            body=row.body,
            version=row.version,
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        )

    async def list_documents(self, ticket: str) -> list[DocumentInfo]:
        """The ticket's documents without their text, in the order they are written."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            if await TicketRepository(session).find(number) is None:
                raise not_found(number)
            rows = await DocumentRepository(session).of(number)
        return document_index(rows)

    async def delete_document(self, ticket: str, name: DocumentName, *, by: str) -> None:
        """Remove the document; records a `document` activity saying so."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number, for_update=True) is None:
                raise not_found(number)
            store = DocumentRepository(session)
            row = await store.find(number, name.value)
            if row is None:
                raise _missing(number, name)
            await store.remove(row)
            record = {"name": name.value, "removed": True}
            await tickets.append_activity(number, (self._clock(), "document", by), record)

    async def put_mock_file(self, ticket: str, name: str, data: bytes, *, by: str) -> MockFileInfo:
        """Keep a mock image under `name`, replacing the one of that name.

        A plain png, jpeg, gif or webp file name; 1 byte to 16 MiB. Records a `mock_file`
        activity with the name and size.
        """
        number = ticket_number(ticket)
        content_type = check_mock(name, len(data))
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number, for_update=True) is None:
                raise not_found(number)
            store = MockFileRepository(session)
            now = self._clock()
            row = await store.find(number, name) or TicketMockFileRow(
                ticket_number=number, name=name
            )
            row.content_type, row.data, row.updated_by, row.updated_at = content_type, data, by, now
            await store.save(row)
            await tickets.append_activity(
                number, (now, "mock_file", by), {"name": name, "size": len(data)}
            )
            return _mock_info(row)

    async def get_mock_file(self, ticket: str, name: str) -> MockFile:
        """The image `name` whole; `NotFoundError` when the ticket has none so named."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            if await TicketRepository(session).find(number) is None:
                raise not_found(number)
            row = None
            if mock_type(name) is not None:
                row = await MockFileRepository(session).find(number, name)
        if row is None:
            raise NotFoundError("no such mock file")
        return MockFile(name=row.name, content_type=row.content_type, data=row.data)

    async def list_mock_files(self, ticket: str) -> list[MockFileInfo]:
        """The ticket's mock images by name, without their bytes."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            if await TicketRepository(session).find(number) is None:
                raise not_found(number)
            return await MockFileRepository(session).infos(number)

    async def delete_mock_file(self, ticket: str, name: str, *, by: str) -> None:
        """Remove the image; records a `mock_file` activity saying so."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number, for_update=True) is None:
                raise not_found(number)
            store = MockFileRepository(session)
            row = await store.find(number, name)
            if row is None:
                raise NotFoundError("no such mock file")
            await store.remove(row)
            record = {"name": name, "removed": True}
            await tickets.append_activity(number, (self._clock(), "mock_file", by), record)
