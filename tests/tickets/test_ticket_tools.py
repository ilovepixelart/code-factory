"""The ticket tools through the MCP client, over the real services and the test database."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from code_factory.memory.module import module as memory_module
from code_factory.memory.service import MemoryService
from code_factory.platform.mcp.scope import TicketRepositories
from code_factory.platform.services import Services
from code_factory.tickets.models import DocumentName, DocumentWrite, NewTicket, Ticket, TicketFields
from code_factory.tickets.module import module as tickets_module
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    QaHoldouts,
    ReviewService,
    TicketService,
)
from mcp_support import OWNER, Called, call, run_actor

MODULES = [tickets_module, memory_module]
REQUIREMENTS = (
    "# CF requirements\n\n## Requirements\n\n| ID | Requirement | Named check |\n|---|---|---|\n"
    "| R1 | The title is shown | test_title |\n"
)


@pytest.fixture
def services(
    tickets: TicketService,
    activity: ActivityService,
    documents: DocumentService,
    reviews: ReviewService,
    memory: MemoryService,
) -> Services:
    registry = Services()
    for key, service in (
        (TicketService, tickets),
        (ActivityService, activity),
        (DocumentService, documents),
        (ReviewService, reviews),
        (MemoryService, memory),
        (TicketRepositories, tickets),
    ):
        registry.add(key, service)
    return registry


async def _as(services: Services, actor: object, tool: str, **arguments: object) -> Called:
    return await call(services, MODULES, actor, tool, **arguments)  # ty: ignore[invalid-argument-type]


async def _other(tickets: TicketService, repository: str = "sample") -> Ticket:
    return await tickets.create(NewTicket(repository=repository, title="Another"), by="owner:test")


async def test_only_the_qa_run_reads_its_private_acceptance_cases(
    services: Services, ticket: Ticket, tmp_path: Path
) -> None:
    private = tmp_path / "qa-holdouts"
    private.mkdir()
    (private / f"{ticket.id}.md").write_text("Private case H1")
    services.add(QaHoldouts, QaHoldouts(tmp_path))

    qa = await _as(services, run_actor("qa", ticket.id), "get_qa_holdout")
    build = await _as(services, run_actor("build", ticket.id), "get_qa_holdout")

    assert qa.ok
    assert "Private case H1" in qa.text
    assert not build.ok
    assert "Private case H1" not in build.text


async def test_a_role_note_counts_after_its_linked_finding_is_fixed(
    services: Services, ticket: Ticket
) -> None:
    note = await _as(services, run_actor("qa", ticket.id), "post_note", text="Retry loses the form")
    assert note.ok
    second = await _as(
        services, run_actor("qa", ticket.id), "post_note", text="An independent note"
    )
    assert second.ok
    review = await _as(
        services,
        run_actor("review", ticket.id),
        "submit_review",
        verdict="changes",
        summary="Fix the retry",
        findings=[
            {"severity": "major", "text": "Retry loses the form", "note_id": note.data["id"]}
        ],
    )
    assert review.ok, review.text
    reviews = services.get(ReviewService)
    since = datetime(2000, 1, 1, tzinfo=UTC).timestamp()
    until = datetime(2099, 1, 1, tzinfo=UTC).timestamp()
    assert await reviews.role_note_outcomes(since, until) == {"qa": (2, 0)}

    await reviews.close_finding(ticket.id, "F1", "fixed", "Retested the retry", by="owner:test")

    assert await reviews.role_note_outcomes(since, until) == {"qa": (2, 1)}


async def test_a_run_reads_its_own_ticket_without_naming_it(
    services: Services, ticket: Ticket
) -> None:
    answer = await _as(services, run_actor("build", ticket.id), "get_ticket")
    assert answer.ok
    assert answer.data["ticket"]["id"] == ticket.id
    assert answer.data["ticket"]["title"] == "A ticket"
    assert answer.data["documents"] == []
    assert [a["kind"] for a in answer.data["recent_activity"]] == ["created"]
    assert answer.data["description_truncated"] is False


async def test_a_long_description_is_cut_and_says_so(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    await tickets.update(ticket.id, TicketFields(description="x" * 9000), by="owner:test")
    answer = await _as(services, run_actor("build", ticket.id), "get_ticket")
    assert len(answer.data["ticket"]["description"]) == 8000
    assert answer.data["description_truncated"] is True


async def test_a_run_may_not_read_another_ticket_and_is_told_the_same_whether_it_exists(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    other = await _other(tickets)
    expected = (
        f"out_of_scope: this run is scoped to {ticket.id}; {{}} is not available to it. "
        "Use ask_question if you need something from another ticket."
    )
    for asked in (other.id, "CF-999999"):
        answer = await _as(services, run_actor("build", ticket.id), "get_ticket", ticket_id=asked)
        assert (answer.ok, answer.text) == (False, expected.format(asked))


async def test_the_owner_must_name_the_ticket(services: Services) -> None:
    answer = await _as(services, OWNER, "get_ticket")
    assert (answer.ok, answer.text) == (
        False,
        "ticket_id is required for the owner; pass the ticket's id, for example CF-12",
    )


async def test_the_owner_reads_any_ticket_and_a_missing_one_is_not_found(
    services: Services, ticket: Ticket
) -> None:
    assert (await _as(services, OWNER, "get_ticket", ticket_id=ticket.id)).ok
    missing = await _as(services, OWNER, "get_ticket", ticket_id="CF-999999")
    assert (missing.ok, "CF-999999" in missing.text) == (False, True)


async def test_listing_pages_the_board_and_filters_by_column(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    second = await _other(tickets)
    await tickets.set_branch(second.id, "ticket/cf-x", by="owner:test")
    everything = await _as(services, OWNER, "list_tickets", limit=1)
    assert [row["id"] for row in everything.data["items"]] == [ticket.id]
    follow = await _as(
        services, OWNER, "list_tickets", limit=1, cursor=everything.data["next_cursor"]
    )
    assert [row["id"] for row in follow.data["items"]] == [second.id]
    assert follow.data["next_cursor"] is None
    build = await _as(services, OWNER, "list_tickets", column="build")
    assert [row["id"] for row in build.data["items"]] == [second.id]


async def test_a_coordinator_lists_its_own_repository_only_and_a_run_cannot_list(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    await _other(tickets, repository="elsewhere")
    seen = await _as(services, run_actor("coordinate", None), "list_tickets")
    assert [row["id"] for row in seen.data["items"]] == [ticket.id]
    refused = await _as(services, run_actor("build", ticket.id), "list_tickets")
    assert (refused.ok, refused.text) == (
        False,
        "forbidden: list_tickets is not available to a build run. whoami says what is.",
    )


async def test_a_run_files_a_follow_up_linked_to_its_ticket_up_to_three(
    services: Services, tickets: TicketService, activity: ActivityService, ticket: Ticket
) -> None:
    run = run_actor("build", ticket.id)
    for number in range(3):
        made = await _as(services, run, "create_ticket", title=f"Follow-up {number}")
        assert (made.ok, made.data["column"]) == (True, "spec")
    created = await tickets.get(made.data["id"])
    assert (created.repository, created.caused_by, created.parent) == ("sample", [ticket.id], "")
    records = (await activity.list_activity(created.id, kinds=["created"])).items
    assert [r.by for r in records] == ["run:r1"]
    fourth = await _as(services, run, "create_ticket", title="One too many")
    assert (fourth.ok, fourth.text) == (
        False,
        "limit: 3 follow-up tickets already created by this run. Put the rest in notes.",
    )


async def test_a_split_run_files_children_of_its_ticket_up_to_fifty(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    run = run_actor("split", ticket.id)
    first = await _as(services, run, "create_ticket", title="Child 1")
    assert (await tickets.get(first.data["id"])).parent == ticket.id
    for number in range(2, 5):  # past the build quota of three
        assert (await _as(services, run, "create_ticket", title=f"Child {number}")).ok


async def test_a_build_run_may_not_choose_a_parent(services: Services, ticket: Ticket) -> None:
    answer = await _as(
        services, run_actor("build", ticket.id), "create_ticket", title="x", parent=ticket.id
    )
    assert (answer.ok, answer.text) == (
        False,
        "forbidden: only a split run, a coordinator or the owner may set parent.",
    )


async def test_the_owner_names_the_repository_and_may_set_a_parent(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    missing = await _as(services, OWNER, "create_ticket", title="x")
    assert (missing.ok, missing.text.startswith("repository is required")) == (False, True)
    made = await _as(
        services, OWNER, "create_ticket", title="Child", repository="sample", parent=ticket.id
    )
    assert (await tickets.get(made.data["id"])).parent == ticket.id


async def test_the_owner_updates_fields_the_branch_and_the_archive_flag(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    done = await _as(
        services,
        OWNER,
        "update_ticket",
        ticket_id=ticket.id,
        fields={"title": "Renamed", "priority": "high"},
        branch="ticket/cf-1",
        archived=True,
    )
    assert done.data == {"id": ticket.id, "changed": ["title", "priority", "branch", "archived"]}
    after = await tickets.get(ticket.id)
    assert (after.title, after.priority, after.branch, after.archived, after.column) == (
        "Renamed",
        "high",
        "ticket/cf-1",
        True,
        "build",
    )
    cleared = await _as(services, OWNER, "update_ticket", ticket_id=ticket.id, branch="")
    assert cleared.data["changed"] == ["branch"]
    assert (await tickets.get(ticket.id)).column == "spec"
    unchanged = await _as(services, OWNER, "update_ticket", ticket_id=ticket.id, archived=True)
    assert unchanged.data["changed"] == []


async def test_a_run_cannot_update_a_ticket(services: Services, ticket: Ticket) -> None:
    answer = await _as(
        services, run_actor("build", ticket.id), "update_ticket", ticket_id=ticket.id
    )
    assert (
        answer.text
        == "forbidden: update_ticket is not available to a build run. whoami says what is."
    )


async def test_activity_lists_newest_first_by_kind_and_in_pages(
    services: Services, ticket: Ticket
) -> None:
    run = run_actor("build", ticket.id)
    await _as(services, run, "post_note", text="first")
    await _as(services, run, "post_note", text="second")
    page = await _as(services, run, "list_activity", kinds=["note"], limit=1)
    assert [item["data"]["text"] for item in page.data["items"]] == ["second"]
    more = await _as(
        services, run, "list_activity", kinds=["note"], limit=1, cursor=page.data["next_cursor"]
    )
    assert [item["data"]["text"] for item in more.data["items"]] == ["first"]
    every = await _as(services, run, "list_activity")
    assert [item["kind"] for item in every.data["items"]] == ["note", "note", "created"]


async def test_a_note_is_recorded_under_the_runs_name_and_a_run_posts_no_diagnosis(
    services: Services, activity: ActivityService, ticket: Ticket
) -> None:
    run = run_actor("build", ticket.id)
    noted = await _as(services, run, "post_note", text="  found a gap ")
    record = (await activity.list_activity(ticket.id, kinds=["note"])).items[0]
    assert (noted.data["id"], record.by, record.data) == (
        record.id,
        "run:r1",
        {"text": "found a gap"},
    )
    refused = await _as(services, run, "post_note", text="stuck", kind="diagnosis")
    assert refused.text == "forbidden: a run may post notes, not diagnoses. Use kind note."
    owner = await _as(
        services, OWNER, "post_note", ticket_id=ticket.id, text="why", kind="diagnosis"
    )
    assert owner.ok


async def test_a_spec_run_writes_requirements_and_reads_them_back_in_pages(
    services: Services, ticket: Ticket
) -> None:
    run = run_actor("spec", ticket.id)
    written = await _as(services, run, "write_document", name="requirements", content=REQUIREMENTS)
    assert written.data == {"name": "requirements", "version": 1}
    page = await _as(services, run, "read_document", name="requirements", offset=5, max_chars=10)
    assert page.data["text"] == REQUIREMENTS[5:15]
    assert (page.data["next_offset"], page.data["total_chars"]) == (15, len(REQUIREMENTS))
    view = await _as(services, run, "get_ticket")
    assert [(d["name"], d["version"]) for d in view.data["documents"]] == [("requirements", 1)]


async def test_a_run_reads_at_most_forty_thousand_characters_at_once(
    services: Services, documents: DocumentService, ticket: Ticket
) -> None:
    await documents.write_document(
        ticket.id,
        DocumentName.NOTES,
        DocumentWrite(content="n" * 60_000),
        by="owner:test",
    )
    run = run_actor("build", ticket.id)
    page = await _as(services, run, "read_document", name="notes", max_chars=40_000)
    over = await _as(services, run, "read_document", name="notes", max_chars=40_001)

    assert (len(page.data["text"]), page.data["next_offset"]) == (40_000, 40_000)
    assert over.text == (
        "bad arguments: max_chars input should be less than or equal to 40000. "
        "Call again within the tool's input schema."
    )


async def test_a_run_writes_only_its_stages_documents(services: Services, ticket: Ticket) -> None:
    build = run_actor("build", ticket.id)
    refused = await _as(services, build, "write_document", name="spec", content="design")
    assert refused.text == "forbidden: a build run may not write spec. Writable here: notes."
    assert (await _as(services, build, "write_document", name="notes", content="a")).ok
    appended = await _as(
        services, build, "write_document", name="notes", content="b", mode="append"
    )
    assert appended.data == {"name": "notes", "version": 2}
    owner = await _as(
        services, OWNER, "write_document", ticket_id=ticket.id, name="review", content="# Review"
    )
    assert owner.ok


async def test_a_stale_write_and_an_invalid_document_say_what_to_do(
    services: Services, ticket: Ticket
) -> None:
    spec = run_actor("spec", ticket.id)
    await _as(services, spec, "write_document", name="requirements", content=REQUIREMENTS)
    stale = await _as(
        services, spec, "write_document", name="requirements", content=REQUIREMENTS, base_version=7
    )
    assert (stale.ok, "version" in stale.text) == (False, True)
    invalid = await _as(services, spec, "write_document", name="uat", content="x" * 3)
    assert invalid.ok
    bad = await _as(
        services, spec, "write_document", name="requirements", content="# none", base_version=1
    )
    assert (bad.ok, "## Requirements" in bad.text) == (False, True)


async def test_a_review_run_submits_a_review_and_other_stages_cannot(
    services: Services, ticket: Ticket
) -> None:
    findings = [{"severity": "blocker", "text": "Title not saved", "requirement_id": "R1"}]
    review = run_actor("review", ticket.id, run_id="rv")
    done = await _as(
        services, review, "submit_review", verdict="changes", summary="One gap", findings=findings
    )
    assert done.data == {"review_version": 1, "findings": [{"id": "F1", "severity": "blocker"}]}
    build = await _as(
        services, run_actor("build", ticket.id), "submit_review", verdict="pass", summary="ok"
    )
    assert (
        build.text
        == "forbidden: submit_review is not available to a build run. whoami says what is."
    )


async def test_a_verdict_and_its_findings_must_agree(services: Services, ticket: Ticket) -> None:
    review = run_actor("review", ticket.id)
    bad = await _as(services, review, "submit_review", verdict="changes", summary="x")
    assert bad.text == "a changes verdict needs at least one finding"
    ok = await _as(services, review, "submit_review", verdict="pass", summary="Good")
    assert ok.data["findings"] == []


async def test_a_build_run_dismisses_a_finding_once_and_a_review_run_cannot(
    services: Services, ticket: Ticket
) -> None:
    findings = [{"severity": "nit", "text": "Long line"}]
    await _as(
        services,
        run_actor("review", ticket.id),
        "submit_review",
        verdict="changes",
        summary="s",
        findings=findings,
    )
    build = run_actor("build", ticket.id, run_id="b1")
    done = await _as(services, build, "dismiss_finding", finding_id="F1", reason="Generated code.")
    assert done.data == {"id": "F1", "reason": "Generated code."}
    again = await _as(services, build, "dismiss_finding", finding_id="F1", reason="Again.")
    assert again.text == "F1 is already dismissed: Generated code."
    review = await _as(
        services, run_actor("review", ticket.id), "dismiss_finding", finding_id="F1", reason="r"
    )
    assert (
        review.text
        == "forbidden: dismiss_finding is not available to a review run. whoami says what is."
    )


@pytest.mark.parametrize(
    "case",
    [
        ("build", "get_ticket", {}),
        ("build", "read_document", {"name": "notes"}),
        ("build", "write_document", {"name": "notes", "content": "x"}),
        ("build", "list_activity", {}),
        ("build", "post_note", {"text": "x"}),
        ("build", "dismiss_finding", {"finding_id": "F1", "reason": "r"}),
        ("review", "submit_review", {"verdict": "pass", "summary": "s"}),
    ],
)
async def test_every_ticket_tool_refuses_another_ticket_to_a_run(
    services: Services,
    tickets: TicketService,
    ticket: Ticket,
    case: tuple[str, str, dict[str, object]],
) -> None:
    stage, tool, arguments = case
    other = await _other(tickets)
    answer = await _as(services, run_actor(stage, ticket.id), tool, ticket_id=other.id, **arguments)
    assert answer.text.startswith(f"out_of_scope: this run is scoped to {ticket.id}; {other.id}")


async def test_a_coordinator_and_a_run_may_not_name_another_repository(
    services: Services, ticket: Ticket
) -> None:
    other = "elsewhere"
    expected = (
        "out_of_scope: this token is scoped to repository sample; elsewhere is not available to it."
    )
    coordinator = run_actor("coordinate", None)
    listed = await _as(services, coordinator, "list_tickets", repository=other)
    assert listed.text == expected
    for actor in (coordinator, run_actor("build", ticket.id)):
        made = await _as(services, actor, "create_ticket", title="x", repository=other)
        assert made.text == expected
    owner = await _as(services, OWNER, "list_tickets", repository=other)
    assert owner.ok


async def test_two_follow_ups_at_once_with_one_slot_left_make_one(
    services: Services, ticket: Ticket
) -> None:
    run = run_actor("build", ticket.id)
    for number in range(2):
        await _as(services, run, "create_ticket", title=f"Follow-up {number}")
    answers = await asyncio.gather(
        *(_as(services, run, "create_ticket", title=f"Racing {n}") for n in range(2))
    )
    assert sorted(a.ok for a in answers) == [False, True]


async def test_an_update_with_an_invalid_branch_changes_nothing(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    answer = await _as(
        services,
        OWNER,
        "update_ticket",
        ticket_id=ticket.id,
        fields={"title": "Renamed"},
        branch="not a branch name",
    )
    assert answer.ok is False
    assert (await tickets.get(ticket.id)).title == "A ticket"


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_ticket", {}),
        ("list_activity", {}),
        ("post_note", {"text": "seen"}),
    ],
)
async def test_a_coordinator_reaches_only_tickets_of_its_repository_and_is_told_alike(
    services: Services,
    tickets: TicketService,
    ticket: Ticket,
    tool: str,
    arguments: dict[str, object],
) -> None:
    coordinator = run_actor("coordinate", None)  # bound to repository sample
    foreign = await _other(tickets, repository="elsewhere")
    expected = "out_of_scope: this token is scoped to repository sample; {} is not available to it."
    for asked in (foreign.id, "CF-999999"):
        answer = await _as(services, coordinator, tool, ticket_id=asked, **arguments)
        assert (answer.ok, answer.text) == (False, expected.format(asked))
    assert (await _as(services, coordinator, tool, ticket_id=ticket.id, **arguments)).ok


async def test_a_coordinator_is_refused_the_document_tools_outright(
    services: Services, ticket: Ticket
) -> None:
    coordinator = run_actor("coordinate", None)
    for tool, arguments in (
        ("read_document", {"name": "notes"}),
        ("write_document", {"name": "notes", "content": "x"}),
    ):
        answer = await _as(services, coordinator, tool, ticket_id=ticket.id, **arguments)
        assert answer.text == (
            f"forbidden: {tool} is not available to a coordinator. whoami says what is."
        )


async def test_the_owner_is_not_bound_to_a_repository(
    services: Services, tickets: TicketService
) -> None:
    foreign = await _other(tickets, repository="elsewhere")
    assert (await _as(services, OWNER, "get_ticket", ticket_id=foreign.id)).ok


async def test_a_page_size_inside_the_bound_lists_and_one_outside_is_refused_before_running(
    services: Services,
) -> None:
    largest = await _as(services, OWNER, "list_tickets", limit=100)
    over = await _as(services, OWNER, "list_tickets", limit=101)
    under = await _as(services, OWNER, "list_tickets", limit=0)

    assert largest.ok
    assert (over.ok, under.ok) == (False, False)
    assert over.text == (
        "bad arguments: limit input should be less than or equal to 100. "
        "Call again within the tool's input schema."
    )
