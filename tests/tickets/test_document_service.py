"""A ticket's documents through the document service, against the test database."""

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.tickets.models import DocumentName, DocumentWrite, Ticket
from code_factory.tickets.service import ActivityService, DocumentService
from ticket_values import NOW, OWNER

SPEC = DocumentName.SPEC
REQUIREMENTS = """## Requirements

| ID | Requirement | Named check |
|---|---|---|
| CF-7-R1 | The title is shown | test_the_title_is_shown |
| CF-7-R2 | The page reads well |  |
"""


def write(content: str, **change: object) -> DocumentWrite:
    return DocumentWrite.model_validate({"content": content, **change})


VALID = REQUIREMENTS.replace("|  |", "| review |")


async def test_a_new_document_is_version_one_and_reads_back_whole(
    documents: DocumentService, ticket: Ticket
) -> None:
    written = await documents.write_document(
        ticket.id, SPEC, write("# Spec\n\nThe design."), by="run-1"
    )
    assert (written.name, written.version) == (SPEC, 1)
    page = await documents.read_document(ticket.id, SPEC)
    assert page.model_dump() == {
        "name": SPEC,
        "version": 1,
        "text": "# Spec\n\nThe design.",
        "offset": 0,
        "next_offset": None,
        "total_chars": 19,
        "updated_by": "run-1",
        "updated_at": NOW,
    }


async def test_a_replace_names_the_version_it_read(
    documents: DocumentService, ticket: Ticket
) -> None:
    await documents.write_document(ticket.id, SPEC, write("first"), by=OWNER)
    second = await documents.write_document(
        ticket.id, SPEC, write("second", base_version=1), by=OWNER
    )
    assert second.version == 2
    assert (await documents.get_document(ticket.id, SPEC)).body == "second"


async def test_a_replace_from_an_older_version_is_a_conflict_and_changes_nothing(
    documents: DocumentService, ticket: Ticket
) -> None:
    await documents.write_document(ticket.id, SPEC, write("first"), by=OWNER)
    await documents.write_document(ticket.id, SPEC, write("second", base_version=1), by=OWNER)
    given = write("stale", base_version=1)
    with pytest.raises(ConflictError, match="spec is at version 2, written from 1"):
        await documents.write_document(ticket.id, SPEC, given, by=OWNER)
    given = write("blind")
    with pytest.raises(ConflictError, match="spec exists at version 2"):
        await documents.write_document(ticket.id, SPEC, given, by=OWNER)
    assert (await documents.get_document(ticket.id, SPEC)).body == "second"


async def test_a_base_version_for_a_document_not_written_yet_is_a_conflict(
    documents: DocumentService, ticket: Ticket
) -> None:
    given = write("text", base_version=3)
    with pytest.raises(ConflictError, match="spec does not exist yet"):
        await documents.write_document(ticket.id, SPEC, given, by=OWNER)


async def test_an_append_adds_a_line_after_the_text_and_needs_no_version(
    documents: DocumentService, ticket: Ticket
) -> None:
    notes = DocumentName.NOTES
    first = await documents.write_document(ticket.id, notes, write("one", mode="append"), by=OWNER)
    second = await documents.write_document(ticket.id, notes, write("two", mode="append"), by=OWNER)
    assert (first.version, second.version) == (1, 2)
    assert (await documents.get_document(ticket.id, notes)).body == "one\ntwo"


async def test_a_long_document_is_read_in_pages(documents: DocumentService, ticket: Ticket) -> None:
    await documents.write_document(ticket.id, SPEC, write("abcdefghij"), by=OWNER)
    first = await documents.read_document(ticket.id, SPEC, offset=0, max_chars=4)
    assert (first.text, first.next_offset, first.total_chars) == ("abcd", 4, 10)
    last = await documents.read_document(ticket.id, SPEC, offset=8, max_chars=4)
    assert (last.text, last.next_offset) == ("ij", None)


async def test_requirements_that_break_their_shape_are_refused_with_the_line(
    documents: DocumentService, ticket: Ticket
) -> None:
    given = write(REQUIREMENTS)
    with pytest.raises(
        BadRequestError, match=r"requirements row 2 \(CF-7-R2\) has no named check \(line 6\)"
    ):
        await documents.write_document(ticket.id, DocumentName.REQUIREMENTS, given, by=OWNER)
    assert await documents.list_documents(ticket.id) == []


async def test_a_document_over_the_limit_is_refused(
    documents: DocumentService, ticket: Ticket
) -> None:
    given = write("x" * 100_001)
    with pytest.raises(BadRequestError, match="a document is at most 100000 characters"):
        await documents.write_document(ticket.id, SPEC, given, by=OWNER)


async def test_the_index_lists_documents_in_writing_order_and_a_delete_removes_one(
    documents: DocumentService, activity: ActivityService, ticket: Ticket
) -> None:
    await documents.write_document(ticket.id, DocumentName.UAT, write("cases"), by=OWNER)
    await documents.write_document(ticket.id, DocumentName.REQUIREMENTS, write(VALID), by=OWNER)
    index = await documents.list_documents(ticket.id)
    assert [(d.name, d.version, d.chars) for d in index] == [
        (DocumentName.REQUIREMENTS, 1, len(VALID)),
        (DocumentName.UAT, 1, 5),
    ]
    await documents.delete_document(ticket.id, DocumentName.UAT, by=OWNER)
    assert [d.name for d in await documents.list_documents(ticket.id)] == [
        DocumentName.REQUIREMENTS
    ]
    records = (await activity.list_activity(ticket.id, kinds=["document"])).items
    assert [r.data for r in records] == [
        {"name": "uat", "version": 1},
        {"name": "requirements", "version": 1},
        {"name": "uat", "removed": True},
    ]


async def test_a_document_that_does_not_exist_is_not_found(
    documents: DocumentService, ticket: Ticket
) -> None:
    with pytest.raises(NotFoundError, match=f"{ticket.id} has no spec"):
        await documents.read_document(ticket.id, SPEC)
    with pytest.raises(NotFoundError, match=f"{ticket.id} has no spec"):
        await documents.delete_document(ticket.id, SPEC, by=OWNER)
    with pytest.raises(NotFoundError, match="CF-999999 does not exist"):
        await documents.list_documents("CF-999999")


async def test_an_append_that_would_grow_a_document_past_the_limit_is_refused(
    documents: DocumentService, ticket: Ticket
) -> None:
    notes = DocumentName.NOTES
    await documents.write_document(ticket.id, notes, write("x" * 99_998), by=OWNER)
    # 99998 characters, the joining newline and 2 more make 100001.
    given = write("yz", mode="append")
    with pytest.raises(
        BadRequestError, match="notes would be 100001 characters, 1 over the limit of 100000"
    ):
        await documents.write_document(ticket.id, notes, given, by=OWNER)
    assert (await documents.get_document(ticket.id, notes)).version == 1


async def test_an_append_that_reaches_the_limit_exactly_is_taken(
    documents: DocumentService, ticket: Ticket
) -> None:
    notes = DocumentName.NOTES
    await documents.write_document(ticket.id, notes, write("x" * 99_997), by=OWNER)
    taken = await documents.write_document(ticket.id, notes, write("yz", mode="append"), by=OWNER)
    assert taken.version == 2
    assert (await documents.read_document(ticket.id, notes)).total_chars == 100_000
