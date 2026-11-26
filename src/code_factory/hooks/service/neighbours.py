"""The hooks ports over the owning modules' services, resolved from the registry at each call."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, override

from code_factory.auth.models import TokenKind
from code_factory.auth.service import AuthService
from code_factory.git.service import GitService
from code_factory.hooks.models import ReleaseFact, TellConfirm
from code_factory.hooks.ports import (
    Checkout,
    MemoryContext,
    MemoryRecall,
    NewBug,
    NewsFact,
    TicketFacts,
    Tickets,
)
from code_factory.memory_extras.models import TicketContext
from code_factory.memory_extras.service import MemoryExtrasService
from code_factory.platform.errors import NotFoundError
from code_factory.platform.process import run_process
from code_factory.platform.services import Services
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.runs.service import PermissionService, RunService
from code_factory.settings.service import SettingsService
from code_factory.talk.models import News
from code_factory.talk.service import TalkService
from code_factory.tickets.models import Activity, NewTicket, Ticket
from code_factory.tickets.service import ActivityService, TicketService

GIT_S = 5.0
SPEND_LIFETIME = timedelta(seconds=1)
PAGE = 100


def _facts(ticket: Ticket) -> TicketFacts:
    return TicketFacts(
        id=ticket.id,
        repository=ticket.repository,
        title=ticket.title,
        stage=str(ticket.column),
        branch=ticket.branch,
        labels=ticket.labels,
    )


class _Neighbour:
    def __init__(self, services: Services) -> None:
        self._services = services


class TalkAdapter(_Neighbour):
    """News of a ticket from the talk module."""

    async def peek(self, ticket_id: str, session_id: str, since: datetime) -> NewsFact | None:
        """`Talk.peek` of the hooks ports."""
        news = await self._services.get(TalkService).peek_news(ticket_id, session_id, since)
        if news is None:
            return None
        confirm = TellConfirm(
            through_post=news.through_post,
            through_answer=news.through_answer,
            message_ids=news.message_ids,
        )
        return NewsFact(text=news.text, confirm=confirm)

    async def confirm(self, ticket_id: str, session_id: str, marks: TellConfirm) -> None:
        """`Talk.confirm` of the hooks ports."""
        news = News(text="", **marks.model_dump())
        await self._services.get(TalkService).confirm_news(ticket_id, session_id, news)


class PermissionsAdapter(_Neighbour):
    """A run's permission requests through the runs module."""

    async def request(
        self,
        run_id: str,
        payload: dict[str, Any],
        *,
        sandboxed: bool,  # noqa: ARG002  # the runs module has no sandboxed allowance yet
        wait: float,
    ) -> dict[str, Any]:
        """`Permissions.request` of the hooks ports."""
        return await self._services.get(PermissionService).request(run_id, payload, wait)

    async def record(
        self,
        run_id: str,
        tool: str,
        *,
        allow: bool,
        by: Literal["policy", "reviewer", "owner"],
        reason: str,
    ) -> None:
        """`Permissions.record` of the hooks ports."""
        permissions = self._services.get(PermissionService)
        await permissions.record_decision(run_id, tool, allow=allow, by=by, reason=reason)

    async def rules(self) -> list[str]:
        """`Permissions.rules` of the hooks ports."""
        return await self._services.get(PermissionService).rules()

    def kind(self, tool: str, tool_input: object) -> str | None:
        """`Permissions.kind` of the hooks ports."""
        return PermissionService.kit.request_kind(tool, tool_input)


class RunsAdapter(_Neighbour):
    """When a run started."""

    async def started(self, run_id: str) -> datetime | None:
        """`Runs.started` of the hooks ports."""
        try:
            return (await self._services.get(RunService).get(run_id)).started_at
        except NotFoundError:
            return None


class TicketsAdapter(_Neighbour, Tickets):
    """Tickets, their history and new bug tickets."""

    @override
    async def get(self, ticket_id: str) -> TicketFacts:
        """`Tickets.get` of the hooks ports."""
        return _facts(await self._services.get(TicketService).get(ticket_id))

    @override
    async def by_branch(self, repository: str, branch: str) -> TicketFacts | None:
        """`Tickets.by_branch` of the hooks ports."""
        found = await self._services.get(TicketService).find_by_branch(repository, branch)
        return _facts(found) if found else None

    @override
    async def requirements(self, ticket_id: str) -> list[str]:
        """`Tickets.requirements` of the hooks ports."""
        return []  # no module keeps a requirements table yet

    @override
    async def record(self, ticket_id: str, kind: str, data: dict[str, object], by: str) -> None:
        """`Tickets.record` of the hooks ports."""
        await self._services.get(TicketService).record_activity(ticket_id, kind, data, by=by)

    @override
    async def by_source(self, repository: str, source: str) -> TicketFacts | None:
        """`Tickets.by_source` of the hooks ports."""
        found = await self._services.get(TicketService).find_by_source(repository, source)
        return _facts(found) if found else None

    @override
    async def reports(self, ticket_id: str) -> int:
        """`Tickets.reports` of the hooks ports."""
        return len(await self._records(ticket_id, ["reported"]))

    @override
    async def create_bug(self, bug: NewBug) -> str:
        """`Tickets.create_bug` of the hooks ports."""
        new = NewTicket(
            repository=bug.repository,
            title=bug.title,
            type="bug",
            description=bug.description,
            source=bug.source,
            caused_by=bug.caused_by,
        )
        return (await self._services.get(TicketService).create(new, by="board")).id

    @override
    async def activity(self) -> list[tuple[str, Activity]]:
        """`Tickets.activity` of the hooks ports."""
        found: list[tuple[str, Activity]] = []
        for ticket in await self._services.get(TicketService).list():
            found += [(ticket.repository, record) for record in await self._records(ticket.id)]
        return found

    async def _records(self, ticket_id: str, kinds: list[str] | None = None) -> list[Activity]:
        activity = self._services.get(ActivityService)
        records: list[Activity] = []
        cursor: str | None = None
        while True:
            page = await activity.list_activity(ticket_id, kinds=kinds, limit=PAGE, cursor=cursor)
            records += page.items
            if page.next_cursor is None:
                return records
            cursor = page.next_cursor


class MemoryAdapter(_Neighbour):
    """What memory gives a session; a run's recall is recorded as a delivery."""

    async def recall(
        self, repository: str, context: MemoryContext, *, ticket_id: str | None, run_id: str | None
    ) -> MemoryRecall:
        """`Memory.recall` of the hooks ports."""
        memory = self._services.get(MemoryExtrasService)
        ctx = TicketContext(
            stage=context.stage, paths=tuple(context.paths), labels=tuple(context.labels)
        )
        if run_id is not None and ticket_id is not None:
            given = await memory.deliver(run_id, ticket_id, repository, ctx)
        else:
            given = await memory.rules_for(repository, ctx)
        return MemoryRecall(
            kept=list(zip(given.received, given.lines, strict=True)),
            left=[(entry, "") for entry in given.left_out],
            overflow=given.overflow_line or None,
            index=list(given.index),
        )


class CheckoutsAdapter(_Neighbour):
    """The tracked repository and branch of a folder, and what a branch changes."""

    async def of(self, cwd: str) -> Checkout | None:
        """`Checkouts.of` of the hooks ports."""
        try:
            root = await self._services.get(SettingsService).main_checkout(Path(cwd))
        except NotFoundError, OSError:
            return None
        tracked = {
            Path(record.path): record.name
            for record in await self._services.get(RepositoryService).list()
        }
        name = tracked.get(root)
        if name is None:
            return None
        result = await run_process(
            ["git", "-C", cwd, "symbolic-ref", "--quiet", "--short", "HEAD"], timeout_s=GIT_S
        )
        branch = result.stdout.decode().strip() if result.code == 0 else ""
        return Checkout(repository=name, branch=branch)

    async def changed(self, repository: str, branch: str) -> list[str]:
        """`Checkouts.changed` of the hooks ports."""
        git = self._services.get(GitService)
        facts = await git.facts(repository)
        if not facts.known or not branch:
            return []
        return await git.changed_paths(repository, facts.default_branch, branch)


class AuthAdapter(_Neighbour):
    """Sign-in values and owner sessions."""

    async def mint(self) -> str:
        """`Auth.mint` of the hooks ports."""
        issued = await self._services.get(AuthService).issue_sign_in_nonce("open")
        return issued.token.get_secret_value()

    async def spend(self, nonce: str) -> None:
        """`Auth.spend` of the hooks ports."""
        auth = self._services.get(AuthService)
        session = await auth.redeem_sign_in_nonce(nonce, lifetime=SPEND_LIFETIME)
        if session is not None:
            await auth.revoke(session.id)

    async def end_sessions(self) -> int:
        """`Auth.end_sessions` of the hooks ports."""
        auth = self._services.get(AuthService)
        ended = 0
        for token in await auth.list_tokens(kinds=[TokenKind.SESSION]):
            ended += await auth.revoke(token.id, kinds=[TokenKind.SESSION])
        return ended


class ReleasesAdapter(_Neighbour):
    """Published releases and the repository's watch window."""

    async def published(self, repository: str) -> list[ReleaseFact]:
        """`Releases.published` of the hooks ports."""
        releases = await self._services.get(ReleaseService).list(repository)
        shipped = [
            ReleaseFact(version=r.version, at=r.published_at.timestamp(), tickets=r.tickets)
            for r in releases
            if r.published_at is not None
        ]
        return sorted(shipped, key=lambda fact: fact.at)

    async def watch_days(self, repository: str) -> int | None:
        """`Releases.watch_days` of the hooks ports."""
        root = await self._services.get(RepositoryService).get(repository)
        config = await self._services.get(SettingsService).load(root)
        if config.release is None or config.release.watch_days is None:
            return None
        return int(config.release.watch_days)


class RepositoriesAdapter(_Neighbour):
    """Whether a repository is tracked."""

    async def exists(self, name: str) -> bool:
        """`Repositories.exists` of the hooks ports."""
        try:
            await self._services.get(RepositoryService).get(name)
        except NotFoundError:
            return False
        return True
