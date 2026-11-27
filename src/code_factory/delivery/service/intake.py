"""GitHub issues of tracked repositories coming in as tickets, once each, ever."""

from code_factory.delivery.adapters.trackers import read_tracker
from code_factory.delivery.models import Tracker
from code_factory.delivery.ports import NewIssueTicket, Switches
from code_factory.delivery.repository import DeliveryRepository
from code_factory.delivery.rules import intake_description, issue_of, triage
from code_factory.delivery.service.base import Collaborators, logger
from code_factory.platform.errors import CodeFactoryError

ISSUE_FIELDS = "number,title,body,url,labels,author"
WRITERS = {"admin", "maintain", "write"}


def _issue_list(switches: Switches) -> list[str]:
    argv = ["issue", "list", "--state", "open", "--limit", "100", "--json", ISSUE_FIELDS]
    if switches.github_label_required and switches.github_label:
        argv += ["--label", switches.github_label]
    return argv


class IntakeMixin(Collaborators):
    """Issue intake."""

    async def poll_intake(self, repository: str | None = None) -> list[str]:
        """Import the open issues the repositories admit; the new ticket ids."""
        names = [repository] if repository is not None else await self._ports.places.names()
        made: list[str] = []
        for name in names:
            try:
                made += await self._intake_one(name)
            except CodeFactoryError as error:
                logger.warning("delivery: intake of %s failed: %s", name, error)
        return made

    async def _intake_one(self, repository: str) -> list[str]:
        switches = await self._ports.places.switches(repository)
        made = [] if not switches.github_issues else await self._github_intake(repository, switches)
        for tracker in switches.trackers:
            try:
                made += await self._tracker_intake(repository, tracker)
            except CodeFactoryError as error:
                logger.warning(
                    "delivery: %s intake of %s failed: %s", tracker.kind, repository, error
                )
        return made

    async def _tracker_intake(self, repository: str, tracker: Tracker) -> list[str]:
        async with self._uow() as session:
            repo = DeliveryRepository(session)
            if not await repo.claim_poll(f"{tracker.kind}:{repository}", self._clock()):
                return []
            imported = await repo.imported_tickets(repository)
        made = []
        for item in await read_tracker(tracker):
            if item.url in imported:
                continue
            ticket = await self._ports.tickets.create(
                NewIssueTicket(
                    repository=repository,
                    title=item.title,
                    description=intake_description(item.url, item.body),
                    source=item.url,
                    type=item.kind,
                    priority=item.priority,
                    labels=item.labels,
                    due=item.due,
                    parent=imported.get(item.parent, ""),
                    blocked_by=[imported[url] for url in item.blocked_by if url in imported],
                )
            )
            imported[item.url] = ticket
            async with self._uow() as session:
                await DeliveryRepository(session).record_intake(
                    repository, item.url, tracker.kind, ticket, self._clock()
                )
            made.append(ticket)
        return made

    async def _github_intake(self, repository: str, switches: Switches) -> list[str]:
        async with self._uow() as session:
            repo = DeliveryRepository(session)
            if not await repo.claim_poll(f"github:{repository}", self._clock()):
                return []
            imported = await repo.imported(repository)
        listed = await self._gh_json(repository, _issue_list(switches))
        origin = (await self._ports.git.remote_url(repository) or "").removesuffix(".git")
        writers: dict[str, bool] = {}
        made: list[str] = []
        for issue in listed if isinstance(listed, list) else []:
            url = str(issue.get("url") or "")
            if url in imported or not issue_of(url, origin):
                continue
            author = str((issue.get("author") or {}).get("login") or "")
            if author not in writers:
                writers[author] = await self._writes(repository, author)
            if not writers[author]:
                continue
            made.append(await self._import(repository, issue, url))
        return made

    async def _writes(self, repository: str, login: str) -> bool:
        if not login or login.endswith("[bot]") or login.startswith("-"):
            return False
        answer = await self._gh_json(
            repository, ["api", f"repos/{{owner}}/{{repo}}/collaborators/{login}/permission"]
        )
        return isinstance(answer, dict) and answer.get("permission") in WRITERS

    async def _import(self, repository: str, issue: dict[str, object], url: str) -> str:
        listed = issue.get("labels")
        labels = [
            str(label.get("name") or "")
            for label in (listed if isinstance(listed, list) else [])
            if isinstance(label, dict)
        ]
        kind, priority = triage(labels)
        ticket = await self._ports.tickets.create(
            NewIssueTicket(
                repository=repository,
                title=str(issue.get("title") or url),
                description=intake_description(url, str(issue.get("body") or "")),
                source=url,
                type=kind,
                priority=priority,
            )
        )
        async with self._uow() as session:
            await DeliveryRepository(session).record_intake(
                repository, url, "github", ticket, self._clock()
            )
        return ticket
