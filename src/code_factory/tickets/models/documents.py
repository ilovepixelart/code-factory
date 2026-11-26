"""A ticket's documents, their pages and writes, and its mock images."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DocumentName(StrEnum):
    """The documents a ticket can have, in the order they are written."""

    REQUIREMENTS = "requirements"
    MOCK = "mock"
    SPEC = "spec"
    UAT = "uat"
    REVIEW = "review"
    NOTES = "notes"


WriteMode = Literal["replace", "append"]


class Problem(BaseModel):
    """One thing wrong with a document, at its line (from 1; 0 for the whole document)."""

    line: int
    message: str


class Document(BaseModel):
    """One of a ticket's documents, whole."""

    ticket_id: str
    name: DocumentName
    body: str
    version: int
    updated_by: str
    updated_at: datetime


class DocumentInfo(BaseModel):
    """A document as a ticket's index lists it: no text."""

    name: DocumentName
    version: int
    chars: int
    updated_by: str
    updated_at: datetime


class DocumentPage(BaseModel):
    """Part of a document's text; `next_offset` continues it, `None` at its end."""

    name: DocumentName
    version: int
    text: str
    offset: int
    next_offset: int | None
    total_chars: int
    updated_by: str
    updated_at: datetime


class DocumentWrite(BaseModel):
    """A write: the whole text, or text to add at the end.

    A `replace` names the version it read (none to create the document); an `append` needs none.
    """

    content: str
    mode: WriteMode = "replace"
    base_version: int | None = Field(default=None, ge=1)


class DocumentWritten(BaseModel):
    """A write that was taken: the document's new version."""

    name: DocumentName
    version: int


class DocHit(BaseModel):
    """A document that holds every word of a search, whole."""

    ticket_id: str
    name: DocumentName
    text: str


class MockFileInfo(BaseModel):
    """A mock image as a ticket's list shows it: no bytes."""

    name: str
    content_type: str
    size: int
    updated_by: str
    updated_at: datetime


class MockFile(BaseModel):
    """A mock image whole, as it is served."""

    name: str
    content_type: str
    data: bytes
