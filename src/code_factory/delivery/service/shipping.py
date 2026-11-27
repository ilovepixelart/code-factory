"""Taking a finished ticket branch to GitHub, and following its pull request."""

from datetime import timedelta

from code_factory.delivery.models import DeliveryEvent, PullView, ShipOutcome
from code_factory.delivery.ports import Candidate
from code_factory.delivery.repository import DeliveryRepository
from code_factory.delivery.rules import attempts, next_retry, open_match, pull_body, ship_due
from code_factory.delivery.service.base import Collaborators, logger
from code_factory.platform.errors import CodeFactoryError
from code_factory.platform.text import screen_secrets

READ_EVERY = timedelta(seconds=60)
SHIP_COLUMNS = {"build", "review"}
LIST_FIELDS = "url,headRefName,headRefOid,baseRefName,isCrossRepository"


def _unrecorded(
    pull: dict[str, object], by_branch: dict[str, Candidate], known: set[str]
) -> tuple[Candidate, str] | None:
    """The ticket and url of an open same-repository pull request not recorded yet."""
    ticket = by_branch.get(str(pull.get("headRefName") or ""))
    url = str(pull.get("url") or "")
    if ticket is None or not url or url in known or pull.get("isCrossRepository"):
        return None
    return ticket, url


class ShippingMixin(Collaborators):
    """Ship, ship added commits, refresh and record pull requests opened by hand."""

    async def ship(self, ticket_id: str, *, retry: bool = False) -> ShipOutcome:
        """Push the branch tip by id and open (or recognise) its pull request.

        `retry` is the owner asking again: a recorded failure of the head no longer holds it.
        """
        ticket = await self._ports.tickets.get(ticket_id)
        pull = await self._pull_of(ticket_id)
        if pull is not None and pull.url and pull.head:
            return ShipOutcome(ticket_id=ticket_id, shipped=False, url=pull.url, reason="shipped")
        return await self._first_ship(ticket, retry=retry)

    async def _first_ship(self, ticket: Candidate, *, retry: bool = False) -> ShipOutcome:
        git, repository = self._ports.git, ticket.repository
        default = await git.default_branch(repository)
        tip, _ = await git.tip(repository, ticket.branch)
        if not tip or not ticket.branch:
            return self._not(ticket, "the branch has no commit")
        if not await git.holds_code(repository, default, tip):
            return self._not(ticket, "the branch holds no code of its own")
        events = await self._events_of(ticket.id)
        if not retry and not ship_due(events, tip, self._clock()):
            return self._not(ticket, "a failed ship of this head waits")
        held = await self._screen(repository, ticket.branch, default, tip)
        if held is not None:
            await self._record(self._event(ticket.id, "ship_failed", head=tip, reason=held))
            return self._not(ticket, held)
        await self._record(self._event(ticket.id, "ship_started", head=tip))
        listed = await self._gh_json(
            repository,
            [
                "pr",
                "list",
                "--head",
                ticket.branch,
                "--base",
                default,
                "--state",
                "open",
                "--json",
                LIST_FIELDS,
            ],
        )
        found = open_match(listed, default)
        if found is not None:
            return await self._adopt(ticket, found, tip)
        return await self._push_and_open(ticket, default, tip, events)

    async def _adopt(self, ticket: Candidate, found: tuple[str, str], tip: str) -> ShipOutcome:
        url, head = found
        if head != tip:
            reason = f"an open pull request {url} holds another head"
            await self._record(self._event(ticket.id, "ship_failed", head=tip, reason=reason))
            return self._not(ticket, reason)
        await self._opened(ticket, url, tip)
        return ShipOutcome(ticket_id=ticket.id, shipped=True, url=url)

    async def _push_and_open(
        self, ticket: Candidate, default: str, tip: str, events: list[DeliveryEvent]
    ) -> ShipOutcome:
        repository = ticket.repository
        try:
            await self._ports.git.push(repository, tip, ticket.branch)
        except CodeFactoryError as error:
            return await self._failed(ticket, tip, str(error), events)
        await self._record(self._event(ticket.id, "ship_pushed", head=tip))
        title = f"{ticket.id}: {ticket.title}"
        body = pull_body(
            ticket.title, [], default, tip, await self._ports.tickets.behaviour(ticket.id)
        )
        answer = await self._gh_in(
            repository,
            [
                "pr",
                "create",
                "--head",
                ticket.branch,
                "--base",
                default,
                "--title",
                title,
                "--body",
                body,
            ],
        )
        if not answer.ok:
            return await self._failed(ticket, tip, answer.reason, events)
        url = answer.stdout.strip().splitlines()[-1] if answer.stdout.strip() else ""
        await self._opened(ticket, url, tip)
        return ShipOutcome(ticket_id=ticket.id, shipped=True, url=url)

    async def _failed(
        self, ticket: Candidate, tip: str, reason: str, events: list[DeliveryEvent]
    ) -> ShipOutcome:
        retry = next_retry(attempts(events, "ship_failed", tip), reason, self._clock())
        await self._record(
            self._event(ticket.id, "ship_failed", head=tip, reason=reason, retry_at=retry)
        )
        return self._not(ticket, reason)

    async def _opened(self, ticket: Candidate, url: str, tip: str) -> None:
        await self._record(self._event(ticket.id, "pull_request", url=url, head=tip))
        await self._read_pull(ticket.id, ticket.repository, url)
        async with self._uow() as session:
            await DeliveryRepository(session).set_shipped(ticket.id, tip)
        await self._ports.checks.queue(ticket.id, tip)

    async def _screen(self, repository: str, branch: str, base: str, tip: str) -> str | None:
        """Why what the push sends is held: a secret in the branch, a message or a path."""
        git = self._ports.git
        places = {"the branch name": branch}
        for number, message in enumerate(await git.messages(repository, base, tip), 1):
            places[f"commit message {number}"] = message
        places["the changed paths"] = "\n".join(await git.paths(repository, base, tip))
        for place, text in places.items():
            found = screen_secrets(text)
            if found:
                return f"the screen held the push: a secret in {place}, line {found[0].line}"
        return None

    def _not(self, ticket: Candidate, reason: str) -> ShipOutcome:
        return ShipOutcome(ticket_id=ticket.id, shipped=False, reason=reason)

    async def ship_added(self, pull: PullView, ticket: Candidate) -> bool:
        """Push the commits a fix added past the shipped head; true when it pushed."""
        git, repository = self._ports.git, pull.repository
        tip, origin = await git.tip(repository, ticket.branch)
        if pull.state != "open" or not pull.shipped_head or not tip or tip == pull.shipped_head:
            return False
        if not await git.descends(repository, pull.shipped_head, tip):
            return False
        if origin and not await git.descends(repository, origin, tip):
            return False
        default = await git.default_branch(repository)
        held = await self._screen(repository, ticket.branch, default, tip)
        if held is not None:
            logger.warning("delivery: %s not pushed: %s", ticket.id, held)
            return False
        if origin != tip:
            await git.push(repository, tip, ticket.branch)
        await self._record(self._event(ticket.id, "branch_pushed", url=pull.url, head=tip))
        async with self._uow() as session:
            await DeliveryRepository(session).set_shipped(ticket.id, tip)
        await self._read_pull(ticket.id, repository, pull.url)
        await self._ports.checks.queue(ticket.id, tip)
        return True

    async def refresh_pulls(self) -> int:
        """Read again every open pull request read more than a minute ago; how many."""
        now, count = self._clock(), 0
        async with self._uow() as session:
            pulls = await DeliveryRepository(session).open_pulls()
        for pull in pulls:
            if now - pull.read_at >= READ_EVERY:
                await self._read_pull(pull.ticket_id, pull.repository, pull.url)
                count += 1
        return count

    async def record_opened(self, candidates: list[Candidate]) -> int:
        """Record pull requests opened by hand for ticket branches, once a minute per repository."""
        recorded = 0
        for repository in {c.repository for c in candidates}:
            async with self._uow() as session:
                repo = DeliveryRepository(session)
                if not await repo.claim_poll(f"pulls:{repository}", self._clock()):
                    continue
                known = await repo.known_urls(repository)
            listed = await self._gh_json(
                repository, ["pr", "list", "--state", "open", "--json", LIST_FIELDS]
            )
            by_branch = {c.branch: c for c in candidates if c.repository == repository}
            for pull in listed if isinstance(listed, list) else []:
                unrecorded = _unrecorded(pull, by_branch, known)
                if unrecorded is None:
                    continue
                ticket, url = unrecorded
                if await self._pull_of(ticket.id) is None:
                    await self._read_pull(ticket.id, repository, url)
                    recorded += 1
        return recorded
