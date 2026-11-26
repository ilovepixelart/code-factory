"""One card of the board: the fields the web app reads, derived from a ticket's facts."""

from datetime import datetime
from typing import Any

from code_factory.board.models import CardFacts, PullFacts
from code_factory.board.rules.words import (
    budget_amount,
    checklist_counts,
    days_in_column,
    due_date,
    due_state,
    trim,
)

DESCRIPTION_LIMIT = 280
_PULL_EXTRAS = ("other_ci", "draft", "conflict", "since", "additions", "deletions", "changed_files")


def card_pull(pull: PullFacts | None) -> dict[str, Any] | None:
    """The card's pull request; a fact the delivery module did not record is absent."""
    if pull is None:
        return None
    shown: dict[str, Any] = {
        "state": pull.state,
        "review": pull.review,
        "ci": pull.ci,
        "head": pull.head,
        "url": pull.url,
        "at": pull.at,
    }
    for name in _PULL_EXTRAS:
        value = getattr(pull, name)
        if value is not None:
            shown[name] = value
    return shown


def _optional(facts: CardFacts) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if facts.runs.spent_estimated:
        extra["spent_estimated"] = True
    if facts.delivery_event is not None:
        extra["delivery_event"] = facts.delivery_event
    if facts.checks_configured:
        extra["checks_configured"] = True
    return extra | facts.queue


def _runs(facts: CardFacts) -> list[dict[str, Any]]:
    return [run.model_dump() for run in facts.runs.runs]


def build_card(facts: CardFacts, now: datetime) -> dict[str, Any]:
    """The card of one ticket, in the order of the answer the app was written against."""
    ticket, placed = facts.ticket, facts.placement
    done, total = checklist_counts(ticket.description)
    ticket_budget = budget_amount(ticket.budget)
    card: dict[str, Any] = {
        "id": ticket.id,
        "title": ticket.title,
        "type": ticket.type,
        "branch": ticket.branch,
        "repository": ticket.repository,
        "stage": placed.stage,
        "evidence_stage": placed.evidence_stage,
        "description": trim(ticket.description, DESCRIPTION_LIMIT),
        "labels": ticket.labels,
        "priority": ticket.priority,
        "assignee": ticket.assignee,
        "due": ticket.due,
        "blocked": ticket.blocked,
        "archived": ticket.archived,
        "rank": ticket.rank,
        "stage_since": facts.stage_since,
        "checklist": [done, total],
        "open_questions": facts.open_questions,
        "sessions": facts.sessions,
        "runs": _runs(facts),
        "repository_path": facts.repository_path,
        "declared": placed.declared,
        "parent": ticket.parent,
        "due_state": due_state(ticket.due, placed.stage, now),
        "days_in_column": days_in_column(facts.stage_since, now),
        "links": {
            "open_blockers": facts.open_blockers,
            "children": facts.children,
            "children_done": facts.children_done,
        },
        "check": facts.check,
        "pull": card_pull(facts.pull),
        "due_date": due_date(ticket.due),
        "spent": 0 if facts.runs.spent is None else facts.runs.spent,
        "budget": ticket_budget if ticket_budget is not None else facts.repository_budget,
        "halted": facts.runs.halted,
        "limited_until": facts.runs.limited_until,
        "hold": None if placed.stage in {"merged", "released"} else placed.hold,
        "subagents": facts.subagents,
    }
    return card | _optional(facts)
