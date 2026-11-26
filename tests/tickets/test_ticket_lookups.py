"""What other modules ask of the ticket service: references, lookups by source and branch,
merged and open tickets, document search, flow facts, and scratch tickets.

Expected values are worked by hand from the specs that request each method (inbox, memory-extras,
metrics, follower): a reference is `id, repository, title, column, labels, rank, branch`, the
lookups answer by exact value, and a source belongs to one ticket per repository.
"""

from datetime import UTC, datetime

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.tickets.models import (
    Column,
    DocHit,
    DocumentName,
    DocumentWrite,
    NewActivity,
    NewTicket,
    PullRequest,
    PullRequestState,
    StageMove,
    Ticket,
    TicketFields,
    TicketFilter,
    TicketRef,
)
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    TicketService,
    is_outside,
)
from ticket_values import NOW, OWNER

REPO = "lookups"


async def make(tickets: TicketService, title: str, **fields: object) -> Ticket:
    new = NewTicket.model_validate({"repository": REPO, "title": title, **fields})
    return await tickets.create(new, by=OWNER)


async def test_a_reference_names_where_the_ticket_stands(tickets: TicketService) -> None:
    made = await make(tickets, "One", labels=["ui"], rank=2)
    await tickets.set_branch(made.id, "ticket/cf-1", by=OWNER)
    assert await tickets.ref_of(made.id) == TicketRef(
        id=made.id,
        repository=REPO,
        title="One",
        column=Column.BUILD,
        labels=["ui"],
        rank=2,
        branch="ticket/cf-1",
    )


async def test_locate_refuses_a_ticket_of_another_repository(tickets: TicketService) -> None:
    made = await make(tickets, "One")
    assert (await tickets.locate(REPO, made.id)).id == made.id
    with pytest.raises(NotFoundError, match="no such ticket"):
        await tickets.locate("elsewhere", made.id)
    with pytest.raises(NotFoundError, match="CF-999999"):
        await tickets.ref_of("CF-999999")


async def test_live_references_leave_out_archived_tickets_in_board_order(
    tickets: TicketService,
) -> None:
    late = await make(tickets, "Late")
    first = await make(tickets, "First", rank=1)
    gone = await make(tickets, "Gone")
    await tickets.archive(gone.id, by=OWNER)
    ids = [r.id for r in await tickets.live_refs() if r.repository == REPO]
    assert ids == [first.id, late.id]


async def test_a_source_belongs_to_one_ticket_per_repository(tickets: TicketService) -> None:
    first = await make(tickets, "From an issue", source="https://example.test/issues/1")
    assert (await tickets.find_by_source(REPO, "https://example.test/issues/1")) == first
    assert await tickets.find_by_source(REPO, "https://example.test/issues/2") is None
    with pytest.raises(ConflictError, match=r"a ticket from https://example\.test/issues/1 exists"):
        await make(tickets, "Again", source="https://example.test/issues/1")
    other = await tickets.create(
        NewTicket(repository="other", title="Same", source="https://example.test/issues/1"),
        by=OWNER,
    )
    assert other.repository == "other"


async def test_an_edit_cannot_give_a_ticket_a_source_another_one_has(
    tickets: TicketService,
) -> None:
    await make(tickets, "One", source="error:abc")
    two = await make(tickets, "Two")
    with pytest.raises(ConflictError, match="a ticket from error:abc exists"):
        await tickets.update(two.id, TicketFields(source="error:abc"), by=OWNER)
    assert (await tickets.get(two.id)).source == ""


async def test_tickets_without_a_source_do_not_collide(tickets: TicketService) -> None:
    await make(tickets, "One")
    await make(tickets, "Two")


async def test_the_sources_of_a_repository_are_listed_once(tickets: TicketService) -> None:
    await make(tickets, "One", source="stall:1")
    await make(tickets, "Two", source="stall:2")
    await make(tickets, "Three")
    assert await tickets.existing_sources(REPO) == frozenset({"stall:1", "stall:2"})
    assert await tickets.existing_sources("nowhere") == frozenset()


async def test_a_branch_finds_its_ticket(tickets: TicketService) -> None:
    made = await make(tickets, "One")
    await tickets.set_branch(made.id, "ticket/cf-77", by=OWNER)
    assert (await tickets.find_by_branch(REPO, "ticket/cf-77")) is not None
    assert await tickets.find_by_branch(REPO, "ticket/cf-78") is None
    assert await tickets.find_by_branch("elsewhere", "ticket/cf-77") is None


async def test_merged_names_the_given_tickets_whose_work_is_merged(tickets: TicketService) -> None:
    done = await make(tickets, "Done")
    pulled = await make(tickets, "Pulled")
    open_one = await make(tickets, "Open")
    await tickets.set_merged(done.id, True, by=OWNER)
    merged_pull = PullRequest(number=3, state=PullRequestState.MERGED)
    await tickets.set_pull_request(pulled.id, merged_pull, by=OWNER)
    ids = [done.id, pulled.id, open_one.id, "CF-999999"]
    assert await tickets.merged(REPO, ids) == frozenset({done.id, pulled.id})
    assert await tickets.merged("elsewhere", ids) == frozenset()
    assert await tickets.merged(REPO, []) == frozenset()


async def test_open_titles_leave_out_archived_and_merged_tickets(tickets: TicketService) -> None:
    keep = await make(tickets, "Keep")
    done = await make(tickets, "Done")
    gone = await make(tickets, "Gone")
    await tickets.set_merged(done.id, True, by=OWNER)
    await tickets.archive(gone.id, by=OWNER)
    assert await tickets.open_titles(REPO) == [(keep.id, "Keep")]


async def test_open_titles_leave_out_a_ticket_whose_pull_request_merged(
    tickets: TicketService,
) -> None:
    keep = await make(tickets, "Keep")
    pulled = await make(tickets, "Pulled")
    await tickets.set_pull_request(
        pulled.id, PullRequest(number=3, state=PullRequestState.MERGED), by=OWNER
    )
    assert await tickets.open_titles(REPO) == [(keep.id, "Keep")]


async def test_documents_are_searched_for_every_word_ignoring_case(
    tickets: TicketService, documents: DocumentService
) -> None:
    one = await make(tickets, "One")
    two = await make(tickets, "Two")
    await documents.write_document(
        one.id, DocumentName.NOTES, DocumentWrite(content="The Cache is warm"), by=OWNER
    )
    await documents.write_document(
        two.id, DocumentName.NOTES, DocumentWrite(content="The cache"), by=OWNER
    )
    hits = await tickets.search_documents(REPO, ["cache", "WARM"], 10)
    assert hits == [DocHit(ticket_id=one.id, name=DocumentName.NOTES, text="The Cache is warm")]
    assert len(await tickets.search_documents(REPO, ["cache"], 10)) == 2
    assert len(await tickets.search_documents(REPO, ["cache"], 1)) == 1
    assert await tickets.search_documents("elsewhere", ["cache"], 10) == []


async def test_a_search_word_is_text_not_a_pattern(
    tickets: TicketService, documents: DocumentService
) -> None:
    one = await make(tickets, "One")
    await documents.write_document(
        one.id, DocumentName.NOTES, DocumentWrite(content="100 percent done"), by=OWNER
    )
    assert await tickets.search_documents(REPO, ["%"], 10) == []
    assert await tickets.search_documents(REPO, ["_"], 10) == []


async def test_flow_facts_carry_the_moves_between_columns(tickets: TicketService) -> None:
    made = await make(tickets, "Flowing")
    child = await make(tickets, "Defect", caused_by=[made.id])
    await tickets.set_branch(made.id, "ticket/cf-5", by=OWNER)
    await tickets.set_merged(made.id, True, by=OWNER)
    [flow] = await tickets.flow_facts(REPO, [made.id])
    assert (flow.id, flow.title, flow.stage, flow.archived, flow.branch) == (
        made.id,
        "Flowing",
        Column.MERGED,
        False,
        "ticket/cf-5",
    )
    assert flow.moves == [StageMove(at=NOW, to=Column.BUILD), StageMove(at=NOW, to=Column.MERGED)]
    [caused] = await tickets.flow_facts(REPO, [child.id])
    assert caused.caused_by == [made.id]
    assert caused.moves == []


async def test_flow_facts_can_be_narrowed_to_columns_and_include_archived_by_default(
    tickets: TicketService,
) -> None:
    building = await make(tickets, "Building")
    waiting = await make(tickets, "Waiting")
    await tickets.set_branch(building.id, "ticket/cf-6", by=OWNER)
    await tickets.archive(waiting.id, by=OWNER)
    everyone = {f.id for f in await tickets.flow_facts(REPO)}
    assert {building.id, waiting.id} <= everyone
    built = await tickets.flow_facts(REPO, None, [Column.BUILD])
    assert [f.id for f in built] == [building.id]


async def test_a_scratch_ticket_is_filed_off_the_board(tickets: TicketService) -> None:
    scratch = await tickets.create_scratch(NewTicket(repository=REPO, title="Eval task"), by="eval")
    assert scratch.archived
    assert scratch.source.startswith("scratch:")
    assert scratch.id not in {t.id for t in await tickets.list()}


@pytest.mark.parametrize(
    "source", ["http://x.test/1", "https://x.test/1", "error:a1", "stall:CF-1", "scorer:daily"]
)
def test_a_source_that_names_something_outside_is_outside(source: str) -> None:
    assert is_outside(source)


@pytest.mark.parametrize("source", ["", "github:1", "errors", "ftp://x.test", "my error:1"])
def test_other_sources_are_not(source: str) -> None:
    assert not is_outside(source)


async def test_another_module_records_a_dotted_kind_at_its_own_moment(
    tickets: TicketService, activity: ActivityService
) -> None:
    moment = datetime(2026, 10, 4, 10, 1, tzinfo=UTC)
    made = await make(tickets, "One")
    taken = await tickets.record_activity(
        made.id, "run.started", {"run": "r-1"}, by="board", at=moment
    )
    assert (taken.kind, taken.by, taken.at, taken.data) == (
        "run.started",
        "board",
        moment,
        {"run": "r-1"},
    )
    assert (await activity.list_activity(made.id, kinds=["run.started"])).items == [taken]


@pytest.mark.parametrize(
    "kind", ["finding", "finding.kept", "finding.dismissed", "finding.closed", "review_submitted"]
)
async def test_the_records_that_decide_a_finding_are_written_by_the_review_only(
    tickets: TicketService, kind: str
) -> None:
    made = await make(tickets, "One")
    with pytest.raises(BadRequestError, match=f"{kind} is written by the review"):
        await tickets.record_activity(made.id, kind, {"id": "F1"}, by="run-1")


@pytest.mark.parametrize("kind", ["run.", ".run", "run..started", "Run.started", "run.Started"])
async def test_a_dotted_kind_is_lower_case_words_between_single_dots(
    tickets: TicketService, kind: str
) -> None:
    made = await make(tickets, "One")
    with pytest.raises(BadRequestError, match="is not a record kind"):
        await tickets.record_activity(made.id, kind, {}, by="board")


async def test_diagnoses_are_listed_newest_first_with_their_author(
    tickets: TicketService,
) -> None:
    one = await make(tickets, "One")
    two = await make(tickets, "Two")
    await tickets.record_note(one.id, "Stuck on review", "diagnosis", by="coordinator")
    await tickets.record_note(one.id, "just a note", "note", by="coordinator")
    await tickets.record_note(two.id, "Blocked by CF-1", "diagnosis", by="coordinator")
    mine = [d for d in await tickets.list_diagnoses() if d.ticket_id in {one.id, two.id}]
    assert [(d.ticket_id, d.author, d.text, d.at) for d in mine] == [
        (two.id, "coordinator", "Blocked by CF-1", NOW),
        (one.id, "coordinator", "Stuck on review", NOW),
    ]


async def test_a_stage_record_with_no_valid_column_is_skipped_by_the_flow(
    tickets: TicketService, activity: ActivityService
) -> None:
    made = await make(tickets, "Flowing")
    await tickets.set_branch(made.id, "ticket/cf-9", by=OWNER)
    await activity.append(made.id, NewActivity(kind="stage", data={}), by="hand")
    await activity.append(made.id, NewActivity(kind="stage", data={"to": "nowhere"}), by="hand")
    [flow] = await tickets.flow_facts(REPO, [made.id])
    assert flow.moves == [StageMove(at=NOW, to=Column.BUILD)]


async def test_a_scratch_ticket_is_in_no_count_list_flow_or_source(
    tickets: TicketService,
) -> None:
    await tickets.create_scratch(NewTicket(repository=REPO, title="Eval task"), by="eval-probe")
    assert await tickets.count_authored("eval-probe", "created") == 0
    assert await tickets.flow_facts(REPO) == []
    assert await tickets.existing_sources(REPO) == frozenset()
    assert await tickets.open_titles(REPO) == []
    assert await tickets.list(TicketFilter(archived=None)) == []


async def test_a_scratch_ticket_is_read_by_its_id_until_deleted(
    tickets: TicketService, activity: ActivityService
) -> None:
    scratch = await tickets.create_scratch(NewTicket(repository=REPO, title="Eval"), by="eval")
    await activity.record_note(scratch.id, "a note", "note", by="eval")
    assert (await tickets.get(scratch.id)).title == "Eval"
    await tickets.delete_scratch(scratch.id)
    with pytest.raises(NotFoundError, match=scratch.id):
        await tickets.get(scratch.id)


async def test_only_a_scratch_ticket_is_deleted(
    tickets: TicketService, activity: ActivityService
) -> None:
    kept = await make(tickets, "Real")
    with pytest.raises(ConflictError, match=f"{kept.id} is not a scratch ticket"):
        await tickets.delete_scratch(kept.id)
    assert (await tickets.get(kept.id)).title == "Real"
    assert len((await activity.list_activity(kept.id)).items) == 1


async def test_deleting_a_scratch_ticket_leaves_another_tickets_history(
    tickets: TicketService, activity: ActivityService
) -> None:
    kept = await make(tickets, "Real")
    scratch = await tickets.create_scratch(NewTicket(repository=REPO, title="Eval"), by="eval")
    await tickets.delete_scratch(scratch.id)
    assert [r.kind for r in (await activity.list_activity(kept.id)).items] == ["created"]
