"""A ticket's mock images, kept as rows and served by the page.

The accepted types and limit are the previous implementation's: png, jpeg, gif or webp by file
extension, never SVG (it can run script when opened as a page), at most 16 MiB, a plain file name
directly under the ticket's mock folder (no path, no leading dot).
"""

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.tickets.models import MockFile, MockFileInfo, Ticket
from code_factory.tickets.service import ActivityService, DocumentService
from ticket_values import NOW, OWNER

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


@pytest.mark.parametrize(
    ("name", "content_type"),
    [
        ("home.png", "image/png"),
        ("Home.PNG", "image/png"),
        ("a.jpg", "image/jpeg"),
        ("a.jpeg", "image/jpeg"),
        ("a.gif", "image/gif"),
        ("a.webp", "image/webp"),
        ("step-1_final.v2.png", "image/png"),
    ],
)
async def test_an_image_is_kept_and_read_back_with_its_type(
    documents: DocumentService, ticket: Ticket, name: str, content_type: str
) -> None:
    info = await documents.put_mock_file(ticket.id, name, PNG, by=OWNER)
    assert info == MockFileInfo(
        name=name, content_type=content_type, size=len(PNG), updated_by=OWNER, updated_at=NOW
    )
    assert await documents.get_mock_file(ticket.id, name) == MockFile(
        name=name, content_type=content_type, data=PNG
    )


@pytest.mark.parametrize(
    "name",
    ["../a.png", "a/b.png", "a\\b.png", ".hidden.png", "a.svg", "a.txt", "noext", "a b.png", ""],
)
async def test_a_name_that_is_not_a_plain_image_file_is_refused(
    documents: DocumentService, ticket: Ticket, name: str
) -> None:
    with pytest.raises(BadRequestError, match="a mock file"):
        await documents.put_mock_file(ticket.id, name, PNG, by=OWNER)
    assert await documents.list_mock_files(ticket.id) == []


async def test_an_image_is_at_most_sixteen_mebibytes_and_not_empty(
    documents: DocumentService, ticket: Ticket
) -> None:
    limit = 16 * 1024 * 1024
    await documents.put_mock_file(ticket.id, "big.png", b"x" * limit, by=OWNER)
    with pytest.raises(BadRequestError, match="at most 16 MiB"):
        await documents.put_mock_file(ticket.id, "bigger.png", b"x" * (limit + 1), by=OWNER)
    with pytest.raises(BadRequestError, match="is empty"):
        await documents.put_mock_file(ticket.id, "empty.png", b"", by=OWNER)


async def test_a_second_put_replaces_the_image(documents: DocumentService, ticket: Ticket) -> None:
    await documents.put_mock_file(ticket.id, "a.png", PNG, by=OWNER)
    await documents.put_mock_file(ticket.id, "a.png", b"new", by="run-1")
    assert (await documents.get_mock_file(ticket.id, "a.png")).data == b"new"
    [info] = await documents.list_mock_files(ticket.id)
    assert (info.size, info.updated_by) == (3, "run-1")


async def test_the_files_of_a_mock_are_listed_by_name(
    documents: DocumentService, ticket: Ticket
) -> None:
    await documents.put_mock_file(ticket.id, "b.png", PNG, by=OWNER)
    await documents.put_mock_file(ticket.id, "a.gif", PNG, by=OWNER)
    assert [i.name for i in await documents.list_mock_files(ticket.id)] == ["a.gif", "b.png"]


@pytest.mark.parametrize("name", ["missing.png", "../a.png", "a.svg"])
async def test_a_file_the_ticket_does_not_have_is_not_found(
    documents: DocumentService, ticket: Ticket, name: str
) -> None:
    with pytest.raises(NotFoundError, match="no such mock file"):
        await documents.get_mock_file(ticket.id, name)


async def test_a_file_is_removed_and_the_history_says_so(
    documents: DocumentService, activity: ActivityService, ticket: Ticket
) -> None:
    await documents.put_mock_file(ticket.id, "a.png", PNG, by=OWNER)
    await documents.delete_mock_file(ticket.id, "a.png", by=OWNER)
    assert await documents.list_mock_files(ticket.id) == []
    with pytest.raises(NotFoundError, match="no such mock file"):
        await documents.delete_mock_file(ticket.id, "a.png", by=OWNER)
    records = (await activity.list_activity(ticket.id, kinds=["mock_file"])).items
    assert [r.data for r in records] == [
        {"name": "a.png", "size": len(PNG)},
        {"name": "a.png", "removed": True},
    ]


async def test_the_files_of_a_ticket_that_does_not_exist_are_not_found(
    documents: DocumentService,
) -> None:
    with pytest.raises(NotFoundError, match="CF-999999"):
        await documents.list_mock_files("CF-999999")
    with pytest.raises(NotFoundError, match="CF-999999"):
        await documents.put_mock_file("CF-999999", "a.png", PNG, by=OWNER)
