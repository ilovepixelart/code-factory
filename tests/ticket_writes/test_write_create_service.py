"""Filing a ticket: what it writes, what it refuses, and that a refusal leaves nothing.

Expected values: the golden answers G[0] to G[6], `ticket_fields.rs` and hand-worked cases.
"""

import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import Column, TicketFilter
from code_factory.tickets.service import ActivityService, TicketService
from write_fakes import FakeGit
from write_values import file

OWNER = "owner:owner"


async def test_a_create_stores_the_normalised_fields_and_records_who_created_it(
    writes: TicketWriteService, tickets: TicketService, activity: ActivityService
) -> None:
    made = await writes.create(
        "sample",
        {
            "title": "  New thing ",
            "type": "bug",
            "labels": "a, b,",
            "priority": "high",
            "due": "2026-11-01",
        },
        OWNER,
    )

    ticket = await tickets.get(made.id)
    assert (ticket.title, ticket.type, ticket.labels, ticket.priority, ticket.due) == (
        "New thing",
        "bug",
        ["a", "b"],
        "high",
        "2026-11-01",
    )
    assert ticket.repository == "sample"
    records = (await activity.list_activity(made.id)).items
    assert [(r.kind, r.by, r.data) for r in records] == [("created", OWNER, {"type": "bug"})]


async def test_a_create_without_a_type_is_a_feature_and_takes_the_next_number(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    first = await writes.create("sample", {"title": "One"}, OWNER)
    second = await writes.create("sample", {"title": "Two"}, OWNER)

    assert (await tickets.get(second.id)).number == (await tickets.get(first.id)).number + 1
    assert (await tickets.get(first.id)).type == "feature"


@pytest.mark.parametrize(
    ("repository", "fields", "sentence"),
    [
        ("nowhere", {"title": "Lost"}, "unknown repository"),
        ("sample", {"title": "Late", "stage": "build"}, "a new ticket starts in Spec"),
        ("sample", {"title": "Epic", "type": "epic"}, "unknown type epic"),
        ("sample", {"title": "Soon", "priority": "soon"}, "unknown priority soon"),
        ("sample", {"title": "Bad day", "due": "2026-13-01"}, "bad due date 2026-13-01"),
        ("sample", {"title": "x", "zeta": "1", "alpha": "1"}, "unknown fields ['alpha', 'zeta']"),
        ("sample", {"title": "x", "rank": "3"}, "unknown fields ['rank']"),
        ("sample", {"title": "x", "repository": "other"}, "unknown fields ['repository']"),
        ("sample", {"title": "a\nb"}, "title holds a line break"),
        ("sample", {"title": "x", "budget": "1__0"}, "budget must be a number of dollars"),
        ("sample", {"title": "x", "parallel": "7"}, "parallel must be 1 to 4"),
        ("sample", {"title": "x", "caused_by": "CF-999999"}, "no ticket CF-999999"),
        ("sample", {"title": "x", "branch": "bad name"}, "bad branch bad name: it holds a space"),
        ("sample", {"title": "  "}, "a ticket needs a title"),
    ],
)
async def test_a_refused_create_names_why_and_burns_no_number(
    writes: TicketWriteService,
    tickets: TicketService,
    repository: str,
    fields: dict[str, str],
    sentence: str,
) -> None:
    before = await file(tickets, "Before")

    with pytest.raises(BadRequestError) as refused:
        await writes.create(repository, fields, OWNER)

    assert str(refused.value).startswith(sentence)
    assert [t.id for t in await tickets.list(TicketFilter(archived=None))] == [before.id]
    after = await writes.create("sample", {"title": "After"}, OWNER)
    assert (await tickets.get(after.id)).number == before.number + 1


async def test_a_create_that_names_a_ticket_to_link_files_it_linked(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    parent = await file(tickets, "Parent")
    blocker = await file(tickets, "Blocker")

    made = await writes.create(
        "sample",
        {
            "title": "Child",
            "parent": parent.id,
            "blocked_by": f" {blocker.id} ,,",
            "caused_by": parent.id,
        },
        OWNER,
    )

    ticket = await tickets.get(made.id)
    assert (ticket.parent, ticket.blocked_by, ticket.caused_by) == (
        parent.id,
        [blocker.id],
        [parent.id],
    )


async def test_the_documents_and_numbers_of_a_create_are_stored(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    made = await writes.create(
        "sample",
        {
            "title": "T",
            "pages": "a, b",
            "tests": "t1",
            "e2e": "e1",
            "parallel": "02",
            "budget": ".5",
            "source": "https://x/1",
            "description": "Why.",
        },
        OWNER,
    )

    ticket = await tickets.get(made.id)
    assert (ticket.pages, ticket.tests, ticket.e2e, ticket.parallel, ticket.budget) == (
        "a, b",
        "t1",
        "e1",
        "2",
        "0.5",
    )
    assert (ticket.source, ticket.description) == ("https://x/1", "Why.")


async def test_a_create_in_archived_state_is_off_the_board(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    made = await writes.create("sample", {"title": "Old", "archived": "true"}, OWNER)

    assert (await tickets.get(made.id)).archived is True
    assert made.id not in [t.id for t in await tickets.list()]


async def test_a_branch_a_ref_holds_is_taken_and_one_no_ref_holds_is_refused(
    writes: TicketWriteService, tickets: TicketService, git: FakeGit
) -> None:
    git.local = frozenset({"feat/here"})
    git.remote = frozenset({"feat/there"})

    here = await writes.create("sample", {"title": "A", "branch": "feat/here"}, OWNER)
    there = await writes.create("sample", {"title": "B", "branch": "feat/there"}, OWNER)
    with pytest.raises(BadRequestError) as refused:
        await writes.create("sample", {"title": "C", "branch": "feat/gone"}, OWNER)

    assert [(await tickets.get(r.id)).column for r in (here, there)] == [Column.BUILD] * 2
    assert str(refused.value) == (
        "no branch feat/gone exists, so the ticket would stay in Spec: code-factory start <ID> "
        "or a Build run makes the ticket's branch from main; set branch once it exists"
    )


async def test_a_repository_whose_branches_cannot_be_read_skips_the_branch_check(
    writes: TicketWriteService, tickets: TicketService, git: FakeGit
) -> None:
    git.known = False

    made = await writes.create("sample", {"title": "A", "branch": "feat/anything"}, OWNER)

    assert (await tickets.get(made.id)).branch == "feat/anything"


async def test_the_duplicate_question_is_appended_to_the_description(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    asked: list[tuple[str, str]] = []

    async def ask(repository: str, title: str) -> str:
        asked.append((repository, title))
        return "Is this CF-3?"

    writes.bind_duplicate_question(ask)

    plain = await writes.create("sample", {"title": " Same "}, OWNER)
    described = await writes.create("sample", {"title": "Same", "description": "Plan.\n"}, OWNER)
    silent = await writes.create("sample", {"title": "Same"}, OWNER, ask_duplicates=False)

    assert asked == [("sample", "Same"), ("sample", "Same")]
    assert (await tickets.get(plain.id)).description == "Is this CF-3?"
    assert (await tickets.get(described.id)).description == "Plan.\n\nIs this CF-3?"
    assert (await tickets.get(silent.id)).description == ""


async def test_an_unbound_duplicate_question_asks_nothing(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    made = await writes.create("sample", {"title": "Same"}, OWNER)

    assert (await tickets.get(made.id)).description == ""
