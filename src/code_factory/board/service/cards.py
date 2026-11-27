"""The cards of a read: each ticket's facts gathered in bulk, then the pure card rule."""

from typing import Any

from code_factory.board.models import CardFacts, PullFacts, TicketRuns
from code_factory.board.rules.card import build_card
from code_factory.board.rules.parts import delivery_event, latest_check, queue_fields, session_chips
from code_factory.board.service.sources import BoardSources
from code_factory.board.service.world import World
from code_factory.platform.text import stamp
from code_factory.tickets.models import Ticket

DEFAULT_BRANCH = "main"


def _own_pull(ticket: Ticket) -> PullFacts | None:
    pull = ticket.pull_request
    return None if pull is None else PullFacts(state=pull.state.value, url=pull.url)


async def card_facts(
    sources: BoardSources,
    world: World,
    tickets: list[Ticket],
) -> list[CardFacts]:
    """The facts of these tickets' cards: one bulk read per source."""
    ids = [t.id for t in tickets]
    asked = await sources.talk.open_counts(ids)
    runs = await sources.runs.card_runs(ids)
    pulls = await sources.delivery.pulls(ids)
    card_pulls = {t.id: pulls.get(t.id) or _own_pull(t) for t in tickets}
    checks = await sources.checks.latest_checks(
        {ticket: pull.head if pull else "" for ticket, pull in card_pulls.items()}
    )
    events = await sources.delivery.events(ids)
    holders = await sources.queue.holders(ids)
    relations = world.relations()
    found = []
    for ticket in tickets:
        repository = world.repositories.get(ticket.repository)
        pull = card_pulls[ticket.id]
        head = pull.head if pull else ""
        found.append(
            CardFacts(
                ticket=ticket,
                placement=world.placement(ticket),
                stage_since=stamp(world.entered(ticket)),
                repository_path=repository.path if repository else "",
                open_questions=asked.get(ticket.id, 0),
                open_blockers=relations.open_blockers(ticket),
                children=len(relations.children(ticket)),
                children_done=relations.children_done(ticket),
                pull=pull,
                check=latest_check(checks.get(ticket.id, []), head, pull),
                runs=runs.get(ticket.id, TicketRuns()),
                repository_budget=repository.budget_usd if repository else None,
                sessions=session_chips(world.sessions, ticket.id, ticket.branch, DEFAULT_BRANCH),
                subagents=[a.model_dump() for a in world.at_work if a.ticket == ticket.id],
                delivery_event=delivery_event(events.get(ticket.id, []), pull, head),
                checks_configured=bool(repository and repository.checks_configured),
                queue=queue_fields(world.queue_plan.get(ticket.id), holders.get(ticket.id)),
            )
        )
    return found


async def build_cards(
    sources: BoardSources, world: World, tickets: list[Ticket]
) -> list[dict[str, Any]]:
    """The cards of these tickets."""
    return [build_card(facts, world.now) for facts in await card_facts(sources, world, tickets)]
