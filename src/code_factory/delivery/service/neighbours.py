"""The delivery ports over the owning modules' services, resolved from the registry per call."""

import logging
import re
from pathlib import Path

from code_factory.agents.service import AgentService
from code_factory.checks.service import CheckService
from code_factory.delivery.models import Tracker
from code_factory.delivery.ports import Candidate, NewIssueTicket, Switches
from code_factory.delivery.rules import behaviour_section, screens_line
from code_factory.git.service import GitService
from code_factory.platform.errors import CodeFactoryError, NotFoundError
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs.service import RunService
from code_factory.screens.models import APPROVED, BEFORE, CAPTURED, CHANGES
from code_factory.settings.models import LINEAR_API, SLACK_API, ships
from code_factory.settings.service import SettingsService
from code_factory.stages.models import Hold
from code_factory.stages.service import StageService
from code_factory.tickets.models import (
    Column,
    DocumentName,
    NewTicket,
    PullRequest,
    PullRequestState,
    Ticket,
)
from code_factory.tickets.service import ActivityService, DocumentService, TicketService

logger = logging.getLogger(__name__)
SHIPPABLE = {Column.BUILD, Column.REVIEW}
BY = "board"
_NUMBER = re.compile(r"/pull/(\d+)$")


def _candidate(ticket: Ticket) -> Candidate:
    return Candidate(
        id=ticket.id,
        repository=ticket.repository,
        title=ticket.title,
        branch=ticket.branch,
        column=str(ticket.column),
        archived=ticket.archived,
        source=ticket.source,
    )


CAPTURE_KINDS = (CAPTURED, APPROVED, CHANGES, BEFORE)
CAPTURES_READ = 100


class _Neighbour:
    def __init__(self, services: Services) -> None:
        self._services = services


class TicketsAdapter(_Neighbour):
    """`Tickets` over the tickets service."""

    async def candidates(self) -> list[Candidate]:
        """Tickets in Build or Review with a branch."""
        found = await self._services.get(TicketService).list()
        return [_candidate(t) for t in found if t.column in SHIPPABLE and t.branch]

    async def get(self, ticket_id: str) -> Candidate:
        """One ticket."""
        return _candidate(await self._services.get(TicketService).get(ticket_id))

    async def create(self, new: NewIssueTicket) -> str:
        """File an imported issue."""
        ticket = NewTicket.model_validate(
            {
                "repository": new.repository,
                "title": new.title,
                "type": new.type,
                "description": new.description,
                "source": new.source,
                "priority": new.priority or None,
                "labels": new.labels or None,
                "due": new.due or None,
                "parent": new.parent or None,
                "blocked_by": new.blocked_by or None,
            }
        )
        return (await self._services.get(TicketService).create(ticket, by="intake")).id

    async def behaviour(self, ticket_id: str) -> str:
        """The ticket's `## Behaviour` notes and what its screen captures are; empty for neither."""
        try:
            notes = await self._services.get(DocumentService).get_document(
                ticket_id, DocumentName.NOTES
            )
        except NotFoundError:
            notes = None
        page = await self._services.get(ActivityService).list_activity(
            ticket_id, kinds=list(CAPTURE_KINDS), limit=CAPTURES_READ, newest_first=True
        )
        records = [(item.kind, dict(item.data)) for item in reversed(page.items)]
        parts = [
            behaviour_section(notes.body) if notes is not None else "",
            screens_line(records, CAPTURE_KINDS),
        ]
        return "\n\n".join(part for part in parts if part)

    async def record_pull(self, ticket_id: str, url: str, state: str) -> None:
        """Give the ticket its pull request; a number-less address or an unread state is left."""
        number = _NUMBER.search(url)
        if number is None or state not in set(PullRequestState):
            return
        pull = PullRequest(number=int(number.group(1)), state=PullRequestState(state), url=url)
        tickets = self._services.get(TicketService)
        if (await tickets.get(ticket_id)).pull_request != pull:
            await tickets.set_pull_request(ticket_id, pull, by=BY)

    async def record_merged(self, ticket_id: str) -> None:
        """Record the merge on the ticket."""
        await self._services.get(TicketService).set_merged(ticket_id, merged=True, by=BY)


class GitAdapter(_Neighbour):
    """`Git` over the git service."""

    async def default_branch(self, repository: str) -> str:
        """The default branch."""
        return (await self._services.get(GitService).facts(repository)).default_branch

    async def tip(self, repository: str, branch: str) -> tuple[str, str]:
        """(local tip, origin tip)."""
        state = await self._services.get(GitService).branch_state(repository, branch)
        return state.tip, state.remote_tip

    async def holds_code(self, repository: str, base: str, tip: str) -> bool:
        """Whether the tip changes code."""
        return await self._services.get(GitService).holds_code(repository, base, tip)

    async def push(self, repository: str, commit: str, branch: str) -> None:
        """Push by id."""
        await self._services.get(GitService).push_commit(repository, commit, branch)

    async def messages(self, repository: str, base: str, tip: str) -> list[str]:
        """The messages of the added commits."""
        entries = await self._services.get(GitService).read_new_commits(repository, base, tip)
        return [entry.message for entry in entries]

    async def paths(self, repository: str, base: str, tip: str) -> list[str]:
        """The changed paths."""
        return await self._services.get(GitService).changed_paths(repository, base, tip)

    async def descends(self, repository: str, older: str, newer: str) -> bool:
        """Whether `newer` holds `older`."""
        return await self._services.get(GitService).is_ancestor(repository, older, newer)

    async def remote_url(self, repository: str) -> str | None:
        """Where origin points."""
        return await self._services.get(GitService).remote_url(repository)

    async def catch_up(self, repository: str) -> None:
        """Fetch origin; a fetch git refuses is the git service's to report."""
        await self._services.get(GitService).catch_up_main(repository)


class ChecksAdapter(_Neighbour):
    """`Checks` over the checks service."""

    async def verdict(self, repository: str, ticket_id: str, head: str) -> str:
        """The board's checks verdict on a head."""
        return await self._services.get(CheckService).verdict(repository, ticket_id, head)

    async def configured(self, repository: str) -> bool:
        """Whether a checks command is set."""
        return await self._services.get(CheckService).configured(repository)

    async def queue(self, ticket_id: str, head: str) -> None:
        """Queue the checks on the head when they are due; one that cannot is logged, not raised."""
        try:
            await self._services.get(CheckService).queue_head(ticket_id, head)
        except CodeFactoryError as error:
            logger.warning(
                "delivery: the checks of %s at %s not queued: %s", ticket_id, head, error
            )


class MergePolicyAdapter(_Neighbour):
    """Read the reviewed head and the repository's owner-merge rules."""

    async def automatic_hold(self, ticket_id: str, head: str) -> Hold | None:
        """An owner-only change takes precedence over waiting for a review."""
        stages = self._services.get(StageService)
        if (reason := await stages.change_hold(ticket_id, head)) is not None:
            return Hold(reason=reason, owner=True)
        runs = await self._services.get(RunService).runs_on_ticket(ticket_id)
        reviews = [run for run in runs if run.stage == "review"]
        return await stages.review_hold(
            ticket_id,
            head,
            [run.head for run in reviews if run.exit_code is not None and run.head],
            review_active=any(run.exit_code is None for run in reviews),
        )


class PlacesAdapter(_Neighbour):
    """`Places` over the repositories and settings services."""

    async def names(self) -> list[str]:
        """Every tracked repository."""
        return [r.name for r in await self._services.get(RepositoryService).list()]

    async def root(self, repository: str) -> Path:
        """The main checkout."""
        return await self._services.get(RepositoryService).get(repository)

    async def switches(self, repository: str) -> Switches:
        """The delivery settings of `config.toml`; ship is on unless `false`, merges wait."""
        config = await self._services.get(SettingsService).load(await self.root(repository))
        agents, intake = config.agents, config.intake
        return Switches(
            ship=ships(agents),
            merge_waits=not (agents is not None and agents.merge_approval is False),
            github_issues=bool(intake and intake.github_issues),
            github_label=intake.github_label or "" if intake is not None else "",
            github_label_required=bool(intake and intake.github_label_required),
            trackers=await self._trackers(repository, intake),
        )

    async def _trackers(self, repository: str, intake: object) -> tuple[Tracker, ...]:
        """The trackers `[intake]` names whose key this machine granted to this repository."""
        if intake is None:
            return ()
        root = str(await self.root(repository))
        read = lambda name: getattr(intake, name, None) or ""  # noqa: E731  # one field by name
        wanted = (
            ("linear", read("linear_token_env"), read("linear_url") or LINEAR_API),
            ("jira", read("jira_token_env"), read("jira_url")),
            ("slack", read("slack_token_env"), read("slack_url") or SLACK_API),
        )
        trackers = []
        for kind, name, url in wanted:
            key = await self._services.get(AgentService).read_key(name) if name else None
            settings = self._services.get(SettingsService)
            grant = await settings.intake_grant(name) if key is not None else None
            if (
                grant is None
                or grant.repository != root
                or grant.url.rstrip("/") != url.rstrip("/")
            ):
                continue
            trackers.append(
                Tracker(
                    kind=kind,
                    url=url,
                    key=key,
                    label=read("linear_label"),
                    assigned=bool(getattr(intake, "linear_assigned", False)),
                    jql=read("jira_jql"),
                    email=read("jira_email"),
                    channel=read("slack_channel"),
                    reaction=read("slack_reaction"),
                )
            )
        return tuple(trackers)
