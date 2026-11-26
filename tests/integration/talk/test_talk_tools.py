"""The question tools through the MCP client, over the talk service and the test database."""

import pytest

from code_factory.platform.mcp.scope import TicketRepositories
from code_factory.platform.services import Services
from code_factory.talk.models import Reply
from code_factory.talk.module import module as talk_module
from code_factory.talk.service import TalkService
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import TicketService
from mcp_support import OWNER, call, run_actor

COLOUR = "Which colour should the button be?"
CHOICES = [{"text": "Blue", "recommended": True, "reason": "matches the brand"}, {"text": "Red"}]


@pytest.fixture
def services(talk: TalkService, tickets: TicketService) -> Services:
    registry = Services()
    registry.add(TalkService, talk)
    registry.add(TicketRepositories, tickets)
    return registry


async def _as(services: Services, actor: object, tool: str, **arguments: object):  # noqa: ANN202
    return await call(services, [talk_module], actor, tool, **arguments)  # ty: ignore[invalid-argument-type]


async def test_a_run_asks_a_question_on_its_ticket_under_its_name(
    services: Services, talk: TalkService, ticket: Ticket
) -> None:
    run = run_actor("build", ticket.id, run_id="r9")
    asked = await _as(services, run, "ask_question", question=COLOUR, choices=CHOICES)
    assert asked.ok
    assert (asked.data["created"], asked.data["status"]) == (True, "open")
    stored = await talk.get(asked.data["question_id"])
    assert (stored.ticket_id, stored.asked_by, stored.run_id, stored.text) == (
        ticket.id,
        "run:r9",
        "r9",
        COLOUR,
    )
    assert [(c.text, c.recommended, c.reason) for c in stored.choices] == [
        ("Blue", True, "matches the brand"),
        ("Red", False, ""),
    ]


async def test_asking_the_same_open_question_again_returns_it(
    services: Services, ticket: Ticket
) -> None:
    run = run_actor("build", ticket.id)
    first = await _as(services, run, "ask_question", question=COLOUR)
    again = await _as(services, run, "ask_question", question=COLOUR)
    assert again.data["question_id"] == first.data["question_id"]
    assert again.data["created"] is False


async def test_a_question_names_the_document_it_is_about_and_may_take_several_picks(
    services: Services, talk: TalkService, ticket: Ticket
) -> None:
    run = run_actor("spec", ticket.id)
    asked = await _as(
        services,
        run,
        "ask_question",
        question="Which formats?",
        choices=[{"text": "CSV"}, {"text": "JSON"}],
        several=True,
        document="requirements",
    )
    stored = await talk.get(asked.data["question_id"])
    assert (stored.document, stored.several) == ("requirements", True)


async def test_a_run_may_not_ask_about_another_ticket_and_the_owner_may_not_ask_at_all(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    other = await tickets.create(NewTicket(repository="sample", title="Other"), by="owner:test")
    scoped = await _as(
        services, run_actor("build", ticket.id), "ask_question", question="x?", ticket_id=other.id
    )
    assert scoped.text.startswith(f"out_of_scope: this run is scoped to {ticket.id}; {other.id}")
    owner = await _as(services, OWNER, "ask_question", question="x?", ticket_id=ticket.id)
    assert (
        owner.text == "forbidden: ask_question is not available to the owner. whoami says what is."
    )


async def test_a_run_lists_its_own_tickets_questions_with_their_answers(
    services: Services, talk: TalkService, ticket: Ticket
) -> None:
    run = run_actor("build", ticket.id)
    asked = await _as(services, run, "ask_question", question=COLOUR, choices=CHOICES)
    open_now = await _as(services, run, "list_questions")
    assert [q["id"] for q in open_now.data["items"]] == [asked.data["question_id"]]
    await talk.answer(
        asked.data["question_id"], Reply(choices=["Blue"]), by="owner:test", channel="http"
    )
    assert (await _as(services, run, "list_questions")).data["items"] == []
    done = await _as(services, run, "list_questions", status="answered")
    assert done.data["items"][0]["answer"]["picked"] == ["Blue"]


async def test_the_owner_lists_every_tickets_open_questions_in_pages(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    other = await tickets.create(NewTicket(repository="sample", title="Other"), by="owner:test")
    for target in (ticket, other):
        await _as(services, run_actor("build", target.id), "ask_question", question="Which?")
    first = await _as(services, OWNER, "list_questions", limit=1)
    assert len(first.data["items"]) == 1
    second = await _as(services, OWNER, "list_questions", limit=1, cursor=first.data["next_cursor"])
    assert {first.data["items"][0]["ticket_id"], second.data["items"][0]["ticket_id"]} == {
        ticket.id,
        other.id,
    }
    assert second.data["next_cursor"] is None


async def test_a_run_and_a_coordinator_cannot_list_questions_of_other_tickets(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    other = await tickets.create(NewTicket(repository="sample", title="Other"), by="owner:test")
    run = await _as(services, run_actor("build", ticket.id), "list_questions", ticket_id=other.id)
    assert run.text.startswith("out_of_scope: this run is scoped to")
    coordinator = await _as(services, run_actor("coordinate", None), "list_questions")
    assert coordinator.text.startswith("ticket_id is required for a coordinator")


async def test_the_owner_answers_by_choice_and_a_second_answer_needs_replace(
    services: Services, talk: TalkService, ticket: Ticket
) -> None:
    run = run_actor("build", ticket.id)
    asked = await _as(services, run, "ask_question", question=COLOUR, choices=CHOICES)
    question_id = asked.data["question_id"]
    done = await _as(services, OWNER, "answer_question", question_id=question_id, choices=["Blue"])
    assert done.data == {
        "question_id": question_id,
        "ticket_id": ticket.id,
        "text": COLOUR,
        "answer": "Blue",
        "status": "answered",
    }
    stored = await talk.get(question_id)
    assert stored.answer is not None
    assert (stored.answer.by, stored.answer.channel) == ("owner:test", "mcp")
    again = await _as(services, OWNER, "answer_question", question_id=question_id, answer="Red")
    assert (again.ok, "already answered" in again.text) == (False, True)
    replaced = await _as(
        services, OWNER, "answer_question", question_id=question_id, choices=["Red"], replace=True
    )
    assert replaced.data["answer"] == "Red"


async def test_a_run_cannot_answer_and_an_unknown_question_is_not_found(
    services: Services, ticket: Ticket
) -> None:
    run = await _as(services, run_actor("build", ticket.id), "answer_question", question_id=1)
    assert (
        run.text
        == "forbidden: answer_question is not available to a build run. whoami says what is."
    )
    missing = await _as(services, OWNER, "answer_question", question_id=999999, answer="x")
    assert (missing.ok, "999999" in missing.text) == (False, True)


async def test_a_coordinator_lists_questions_of_its_repository_only(
    services: Services, tickets: TicketService, ticket: Ticket
) -> None:
    foreign = await tickets.create(
        NewTicket(repository="elsewhere", title="Foreign"), by="owner:test"
    )
    coordinator = run_actor("coordinate", None)
    expected = "out_of_scope: this token is scoped to repository sample; {} is not available to it."
    for asked in (foreign.id, "CF-999999"):
        answer = await _as(services, coordinator, "list_questions", ticket_id=asked)
        assert (answer.ok, answer.text) == (False, expected.format(asked))
    assert (await _as(services, coordinator, "list_questions", ticket_id=ticket.id)).ok
