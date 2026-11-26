"""What the tickets tables refuse by themselves, whatever code writes to them."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.tickets.models import Ticket


async def test_a_ticket_number_comes_only_from_the_sequence(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError, match="cannot insert a non-DEFAULT value into column"):
        await db_session.execute(
            text("insert into tickets (number, repository, title) values (7, 'sample', 'Seven')")
        )


async def _insert_mock(db_session: AsyncSession, number: int, row: tuple[str, str, bytes]) -> None:
    name, content_type, data = row
    await db_session.execute(
        text(
            "insert into ticket_mock_files (ticket_number, name, content_type, data) "
            "values (:n, :name, :type, :data)"
        ),
        {"n": number, "name": name, "type": content_type, "data": data},
    )


@pytest.mark.parametrize(
    ("row", "constraint"),
    [
        (("a.png", "image/svg+xml", b"x"), "known_content_type"),
        (("a.png", "text/html", b"x"), "known_content_type"),
        (("a.svg", "image/png", b"x"), "image_name"),
        (("noext", "image/png", b"x"), "image_name"),
        (("a.png", "image/png", b""), "has_content"),
    ],
)
async def test_a_mock_row_the_service_would_refuse_is_refused_by_the_table(
    db_session: AsyncSession, ticket: Ticket, row: tuple[str, str, bytes], constraint: str
) -> None:
    number = int(ticket.id.removeprefix("CF-"))
    savepoint = db_session.begin_nested()
    with pytest.raises(DBAPIError, match=constraint):
        async with savepoint:
            await _insert_mock(db_session, number, row)


@pytest.mark.parametrize(
    "row",
    [
        ("a.png", "image/png", b"x"),
        ("A.JPG", "image/jpeg", b"x"),
        ("a.jpeg", "image/jpeg", b"x"),
        ("a.gif", "image/gif", b"x"),
        ("a.webp", "image/webp", b"x"),
    ],
)
async def test_a_mock_row_of_each_allowed_image_type_is_kept(
    db_session: AsyncSession, ticket: Ticket, row: tuple[str, str, bytes]
) -> None:
    await _insert_mock(db_session, int(ticket.id.removeprefix("CF-")), row)
