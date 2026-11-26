"""The `board` sample: the world the browser tests and the contract tests start from."""

from fastapi import FastAPI

from code_factory.memory.models import MemoryFilter
from code_factory.memory.service import MemoryService
from code_factory.sample.service import SampleService
from code_factory.tickets.models import Column, DocumentName, TicketFilter
from code_factory.tickets.service import DocumentService, TicketService


async def _load(app: FastAPI, name: str) -> None:
    await app.state.services.get(SampleService).load(name)


async def test_the_board_sample_files_tickets_in_two_repositories_in_the_columns_the_facts_give(
    app: FastAPI,
) -> None:
    await _load(app, "board")
    tickets = await app.state.services.get(TicketService).list(TicketFilter(archived=None))

    by_title = {t.title: t for t in tickets}
    assert {t.repository for t in tickets} == {"sample", "second"}
    assert by_title["A bug in flight"].column is Column.BUILD
    assert by_title["Merged already"].column is Column.MERGED
    assert by_title["Specs written"].column is Column.SPEC
    assert by_title["Archived"].archived is True
    assert by_title["A bug in flight"].parent == by_title["Specs written"].id
    assert by_title["Worked on main"].blocked_by == [by_title["A bug in flight"].id]


async def test_the_board_sample_gives_the_first_ticket_its_documents(app: FastAPI) -> None:
    await _load(app, "board")
    services = app.state.services
    first = next(t for t in await services.get(TicketService).list() if t.title == "Specs written")
    index = await services.get(DocumentService).list_documents(first.id)
    assert [d.name for d in index] == [
        DocumentName.REQUIREMENTS,
        DocumentName.SPEC,
        DocumentName.UAT,
    ]


async def test_the_board_sample_holds_three_unreviewed_memory_entries(app: FastAPI) -> None:
    await _load(app, "board")
    entries = await app.state.services.get(MemoryService).list(MemoryFilter())
    assert sorted((e.kind, e.reviewed) for e in entries) == [
        ("decision", ""),
        ("lesson", ""),
        ("rule", ""),
    ]
