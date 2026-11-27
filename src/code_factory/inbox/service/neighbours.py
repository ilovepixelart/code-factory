"""The inbox's sources over the owning modules' services, resolved from the registry per call."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from code_factory.checks.service import CheckService
from code_factory.delivery.models import PullView
from code_factory.delivery.service import DeliveryService
from code_factory.follower.service import QueueService
from code_factory.inbox.models import Item, Sections, TicketRef
from code_factory.inbox.rules import permission_item
from code_factory.memory.models import MemoryFilter
from code_factory.memory.service import MemoryService
from code_factory.platform.errors import NotFoundError
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs.service import HALTED, PermissionService, RunService
from code_factory.screens.service import ScreensService
from code_factory.settings.models import ConfigUnjudgedError
from code_factory.settings.service import SettingsService
from code_factory.talk.models import QuestionFilter
from code_factory.talk.service import TalkService
from code_factory.tickets.service import TicketService

STOPPED_WINDOW = timedelta(days=30)
PULL_IDLE_AFTER = timedelta(days=2)
PAGE = 100
NOT_STARTED = "not started: "


class InboxSources:
    """Each section's items from the module that owns its facts."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def sections(self) -> Sections:
        """Build the page's items with ticket references shared within this read."""
        return await _InboxRead(self._services).sections(compact=False)

    async def counted_sections(self) -> Sections:
        """Build just the items the badge and the board count."""
        return await _InboxRead(self._services).sections(compact=True)


class _InboxRead:
    def __init__(self, services: Services) -> None:
        self._services = services
        self._refs: dict[str, TicketRef | None] = {}

    async def _ref(self, ticket_id: str) -> TicketRef | None:
        if ticket_id not in self._refs:
            try:
                t = await self._services.get(TicketService).get(ticket_id)
            except NotFoundError:
                self._refs[ticket_id] = None
            else:
                self._refs[ticket_id] = TicketRef(repository=t.repository, id=t.id, title=t.title)
        return self._refs[ticket_id]

    async def sections(self, *, compact: bool) -> Sections:
        now = datetime.now(UTC)
        counted = {
            "main": await self._main(),
            "questions": await self._questions(compact=compact),
            "permissions": await self._permissions(now, compact=compact),
            "stopped": await self._stopped(now),
            "screens": await self._screens(compact=compact),
            **await self._pulls(now),
        }
        if compact:
            return counted
        return counted | {
            "rules": await self._rules(),
            "memory": await self._memory(),
            "sessions": [],
            "reviews": [],
            "diagnoses": await self._diagnoses(),
        }

    async def _main(self) -> list[Item]:
        failing = await self._services.get(CheckService).failing_default_branches()
        return [
            Item(since=f.at.timestamp(), main=f.model_dump(mode="json", exclude={"at"}))
            for f in failing
        ]

    async def _questions(self, *, compact: bool) -> list[Item]:
        talk = self._services.get(TalkService)
        items: list[Item] = []
        cursor: str | None = None
        while True:
            page = await talk.list(QuestionFilter(status="open"), limit=PAGE, cursor=cursor)
            for q in page.items:
                ref = await self._ref(q.ticket_id)
                question = {"text": q.text} if compact else q.shown()
                items.append(Item(since=q.created_at.timestamp(), ticket=ref, question=question))
            cursor = page.next_cursor
            if cursor is None:
                return items

    async def _permissions(self, now: datetime, *, compact: bool) -> list[Item]:
        permissions = self._services.get(PermissionService)
        tallies = {} if compact else await permissions.answered_counts()
        items = []
        for r in await permissions.pending(now):
            words = permission_item(r.model_dump(), tallies.get(r.kind or ""))
            items.append(
                Item(
                    since=r.requested_at.timestamp(),
                    kind="permission",
                    ticket=await self._ref(r.ticket_key),
                    request={"id": r.id, "tool": r.tool, "summary": r.summary},
                    reason=words["reason"],
                    note=words["note"],
                )
            )
        return items

    async def _screens(self, *, compact: bool) -> list[Item]:
        waiting = await self._services.get(ScreensService).waiting()
        return [
            Item(
                since=shot.at.timestamp(),
                kind="screens",
                ticket=await self._ref(shot.ticket),
                reason=shot.tree,
                images=[] if compact else list(shot.images),
            )
            for shot in waiting
        ]

    async def _rules(self) -> list[Item]:
        suggested = await self._services.get(PermissionService).suggested()
        return [Item(kind="rule", reason=kind, count=count) for kind, count in suggested]

    async def _memory(self) -> list[Item]:
        entries = await self._services.get(MemoryService).list(MemoryFilter(status="proposed"))
        keys = ("repository", "id", "kind", "statement", "why", "source", "guard")
        return [
            Item(
                since=datetime.combine(e.date, datetime.min.time(), UTC).timestamp(),
                memory={k: getattr(e, k) for k in keys},
            )
            for e in entries
        ]

    async def _stopped(self, now: datetime) -> list[Item]:
        runs = self._services.get(RunService)
        latest: dict[str, tuple[datetime, str]] = {}
        for run in await runs.runs_since(now - STOPPED_WINDOW):
            ended = run.ended_at or run.started_at
            if run.ticket_key not in latest or ended >= latest[run.ticket_key][0]:
                latest[run.ticket_key] = (ended, run.halted if run.exit_code is not None else "")
        # A start the hold refused says to resume; once agents may start again it is not stopped.
        held = await runs.halted_at() is not None
        items = [
            Item(since=ended.timestamp(), reason=halted, ticket=await self._ref(ticket))
            for ticket, (ended, halted) in latest.items()
            if halted and (held or halted != HALTED)
        ]
        for ticket, note in (await self._services.get(QueueService).plan()).items():
            if note.startswith(NOT_STARTED):
                items.append(
                    Item(reason=note.removeprefix(NOT_STARTED), ticket=await self._ref(ticket))
                )
        return [i for i in items if i.ticket is not None]

    async def _waits(self, repository: str) -> bool:
        root = await self._services.get(RepositoryService).get(repository)
        try:
            config = await self._services.get(SettingsService).load(Path(root))
        except ConfigUnjudgedError:
            return True
        return not (config.agents is not None and config.agents.merge_approval is False)

    async def _pulls(self, now: datetime) -> dict[str, list[Item]]:
        failing: list[Item] = []
        mergeable: list[Item] = []
        idle: list[Item] = []
        delivery = self._services.get(DeliveryService)
        for pull in await delivery.open_pulls():
            ref = await self._ref(pull.ticket_id)
            if ref is None:
                continue
            if pull.ci == "failed":
                failing.append(self._pull_item(pull, ref, "failing"))
                continue
            if (merge := await self._merge_item(pull, ref)) is not None:
                mergeable.append(merge)
                continue
            if (since := _idle_since(pull, now)) is not None:
                idle.append(Item(since=since, kind="idle", reason=pull.url, ticket=ref))
        return {"mergeable": mergeable, "failing": failing, "idle": idle}

    async def _merge_item(self, pull: PullView, ref: TicketRef) -> Item | None:
        """The inbox item asking the owner to merge `pull`, when it is green and checked."""
        if not (_green(pull) and await self._checked(pull)):
            return None
        if await self._waits(pull.repository):
            return self._pull_item(pull, ref, "merge")
        if note := self._services.get(DeliveryService).owner_hold(pull.ticket_id, pull.head):
            return self._pull_item(pull, ref, "merge", note=note)
        return None

    async def _checked(self, pull: PullView) -> bool:
        """Whether the board's checks passed on the head, as the merge needs when they are set."""
        checks = self._services.get(CheckService)
        if not await checks.configured(pull.repository):
            return True
        return await checks.verdict(pull.repository, pull.ticket_id, pull.head) == "passed"

    @staticmethod
    def _pull_item(pull: PullView, ref: TicketRef, kind: str, *, note: str = "") -> Item:
        size = None
        if pull.additions is not None and pull.deletions is not None:
            size = {
                "additions": pull.additions,
                "deletions": pull.deletions,
                "changed_files": pull.changed_files or 0,
            }
        return Item(
            since=pull.since.timestamp(),
            kind=kind,
            reason=pull.url,
            ticket=ref,
            size=size,
            note=note,
        )

    async def _diagnoses(self) -> list[Item]:
        found = await self._services.get(TicketService).list_diagnoses()
        return [
            Item(
                since=d.at.timestamp(),
                ticket=await self._ref(d.ticket_id),
                diagnosis={"author": d.author, "text": d.text},
            )
            for d in found
        ]


def _idle_since(pull: PullView, now: datetime) -> float | None:
    """When the pull last moved, if it is a non-draft one that has waited long enough."""
    if pull.draft or pull.updated_on_host is None:
        return None
    if now - pull.updated_on_host < PULL_IDLE_AFTER:
        return None
    return pull.updated_on_host.timestamp()


def _green(pull: PullView) -> bool:
    return (
        pull.ci in {"passed", "none"}
        and not pull.draft
        and bool(pull.shipped_head)
        and pull.head == pull.shipped_head
    )
