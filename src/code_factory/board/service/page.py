"""One ticket's page: its card, documents, history and proof, assembled from the services."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import anyio
from anyio import CapacityLimiter

from code_factory.board.models import CheckRecord, RepositoryFacts, TicketRuns
from code_factory.board.rules.budget import month_bounds, month_budget
from code_factory.board.rules.card import build_card
from code_factory.board.rules.fields import ticket_fields
from code_factory.board.rules.page import (
    capture_state,
    column_seconds,
    conflict_of,
    evidence_summary,
    fold_activity,
)
from code_factory.board.rules.talk import talk_line
from code_factory.board.service.cards import card_facts
from code_factory.board.service.sources import BoardSources
from code_factory.board.service.world import World
from code_factory.platform.errors import NotFoundError
from code_factory.platform.text.markdown import INLINE_LIMIT, render
from code_factory.tickets.models import ActivityEntry, DocumentName, Ticket
from code_factory.tickets.service import merge_entries

FEED_SIZE = 100
LOG_LINES = 40
TALK_PAGE = 100
TALK_READ_MAX = 1000
_RENDERS = CapacityLimiter(2)
_PAGE_DOCUMENTS = (
    DocumentName.REQUIREMENTS,
    DocumentName.MOCK,
    DocumentName.SPEC,
    DocumentName.UAT,
)


async def html_of(text: str) -> str:
    """Markdown as safe HTML; text past the inline limit renders in a worker thread."""
    if len(text) <= INLINE_LIMIT:
        return render(text)
    return await anyio.to_thread.run_sync(render, text, limiter=_RENDERS)


def _linked(world: World, ids: Sequence[str]) -> dict[str, dict[str, str]]:
    """Each linked ticket the board holds, whatever its repository: where it is and what it is."""
    by_id = {t.id: t for t in world.tickets}
    return {
        i: {"repository": t.repository, "title": t.title, "stage": world.stage_of(t)}
        for i in ids
        if (t := by_id.get(i))
    }


class PageReader:
    """Builds the page of one ticket from every source the board reads."""

    def __init__(self, sources: BoardSources) -> None:
        self._sources = sources

    async def page(self, world: World, ticket: Ticket) -> dict[str, Any]:
        """The page: its keys in the order the web app was written against."""
        sources = self._sources
        repository = world.repositories.get(ticket.repository)
        checks = await sources.checks.latest_checks([ticket.id])
        [facts] = await card_facts(sources, world, [ticket], checks)
        history = await sources.activity.entries(ticket.id)
        records = checks.get(ticket.id, [])
        card = build_card(facts, world.now)
        spent = await self._spent(facts.runs, repository, card["budget"])
        documents, requirements = await self._documents(ticket)
        placed = world.placement(ticket)
        assessed = world.placements.get(ticket.id)
        same = [t for t in world.tickets if t.repository == ticket.repository]
        link = world.relations().link(ticket)
        return {
            **spent,
            "ticket": ticket_fields(ticket, world.entered(ticket), placed.declared),
            "repository": ticket.repository,
            "work_done": assessed.work_done if assessed else False,
            "checklist": [item.model_dump() for item in assessed.checklist] if assessed else [],
            "summary": await self._summary(ticket, history, requirements),
            "current_stage": placed.stage,
            "questions": [
                q.on_ticket()
                for q in await sources.talk.list_for_ticket(ticket.id)
                if q.status != "withdrawn"
            ],
            "documents": documents,
            "plan": None,
            "link": link,
            "titles": {t.id: t.title for t in same},
            "stages_by_id": {t.id: world.stage_of(t) for t in same},
            "linked": _linked(
                world, [link["parent"], *link["child_ids"], *ticket.blocked_by, *link["blocks"]]
            ),
            "description_html": await html_of(ticket.description) if ticket.description else "",
            **await self._check(ticket, records),
            "checks_configured": bool(repository and repository.checks_configured),
            "activity": await self._activity(ticket.id, history),
            "checking": ticket.id in await sources.checks.running([ticket.id]),
            "month_budget": await self._month_budget(ticket.repository, world),
            "subagents": facts.subagents,
            "card": card,
            "columns": column_seconds(history, world.now),
            "branch": ticket.branch,
            "status": {
                "conflict": conflict_of(history, facts.pull.head)
                if facts.pull and facts.pull.head
                else None,
                "capture": capture_state(history),
            },
        }

    async def summary(self, ticket: Ticket) -> dict[str, Any]:
        """What the ticket proved: for the pull request body as well as the page."""
        history = await self._sources.activity.entries(ticket.id)
        _, requirements = await self._documents(ticket)
        return await self._summary(ticket, history, requirements)

    async def _summary(
        self, ticket: Ticket, history: list[ActivityEntry], requirements: str
    ) -> dict[str, Any]:
        verdict = await self._sources.reviews.latest_review(ticket.id)
        return evidence_summary(history, verdict.verdict if verdict else "", requirements)

    async def _spent(
        self, runs: TicketRuns, repository: RepositoryFacts | None, budget: float | None
    ) -> dict[str, Any]:
        records = await self._sources.runs.run_records([r.id for r in runs.runs])
        shown = {
            "runs": [
                {
                    **run.model_dump(),
                    **(records[run.id].model_dump() if run.id in records else {}),
                }
                for run in runs.runs
            ],
            "spent": 0 if runs.spent is None else runs.spent,
        }
        if runs.spent_estimated:
            shown["spent_estimated"] = True
        return shown | {
            "cost": runs.cost.model_dump(),
            "budget": budget,
            "default_budget": repository.budget_usd if repository else None,
            "halted": runs.halted,
        }

    async def _check(self, ticket: Ticket, records: Sequence[CheckRecord]) -> dict[str, Any]:
        latest = records[-1] if records else None
        failed = latest is not None and latest.exit_code != 0
        return {
            "check": None
            if latest is None
            else latest.model_dump(include={"at", "commit", "exit_code", "log", "tree"}),
            "check_log": await self._sources.checks.log_tail(ticket.id, LOG_LINES)
            if failed
            else "",
        }

    async def _documents(self, ticket: Ticket) -> tuple[list[dict[str, Any]], str]:
        shown: list[dict[str, Any]] = []
        requirements = ""
        for name in _PAGE_DOCUMENTS:
            if name is DocumentName.MOCK and "ui" not in ticket.labels:
                continue
            try:
                text = (await self._sources.documents.get_document(ticket.id, name)).body
            except NotFoundError:
                text = ""
            if name is DocumentName.REQUIREMENTS:
                requirements = text
            item: dict[str, Any] = {
                "stage": name.value,
                "html": await html_of(text) if text.strip() else None,
            }
            if name is DocumentName.MOCK:
                files = await self._sources.documents.list_mock_files(ticket.id)
                item["files"] = [f.name for f in files]
            shown.append(item)
        return shown, requirements

    async def _talk(self, ticket_id: str) -> list[ActivityEntry]:
        lines: list[ActivityEntry] = []
        cursor = None
        while len(lines) < TALK_READ_MAX:
            page = await self._sources.talk.activity_entries(
                ticket_id, limit=TALK_PAGE, cursor=cursor
            )
            lines += [talk_line(record) for record in page.items]
            cursor = page.next_cursor
            if cursor is None:
                break
        return lines

    async def _activity(self, ticket_id: str, history: list[ActivityEntry]) -> list[dict[str, Any]]:
        """The newest `FEED_SIZE` lines of the history and the talk, folded, newest first."""
        merged = merge_entries([history, await self._talk(ticket_id)])
        folded = fold_activity(merged)[:FEED_SIZE]
        records = await self._sources.runs.run_records(
            [e["run"] for e in folded if e["kind"] == "run"]
        )
        for entry in folded:
            found = records.get(entry["run"]) if entry["kind"] == "run" else None
            if found is not None:
                entry |= {k: v for k, v in found.model_dump().items() if v is not None}
        return folded

    async def month_spent(self, repository: str, now: datetime) -> float:
        """What the repository's runs started this UTC month cost."""
        start, following = month_bounds(now)
        return await self._sources.runs.cost_between(repository, start, following)

    async def _month_budget(self, repository: str, world: World) -> dict[str, Any] | None:
        facts = world.repositories.get(repository)
        if facts is None or facts.monthly_budget_usd is None:
            return None
        spent = await self.month_spent(repository, world.now)
        return month_budget(spent, facts.monthly_budget_usd, world.now)
