"""The `delivery` module as the platform sees it."""

import asyncio
import logging
import os
import re
from collections.abc import Sequence

from code_factory.board.models import ActivityRecord, PullFacts
from code_factory.board.service import CardDelivery
from code_factory.checks.models import PullHead
from code_factory.delivery import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.delivery.cli import delivery_command
from code_factory.delivery.models import DeliveryEvent
from code_factory.delivery.ports import DeliveryPorts
from code_factory.delivery.routes import router
from code_factory.delivery.service import DeliveryForge, DeliveryService
from code_factory.delivery.service.neighbours import (
    ChecksAdapter,
    GitAdapter,
    MergePolicyAdapter,
    PlacesAdapter,
    TicketsAdapter,
)
from code_factory.factory.models import PullFact, PullState
from code_factory.git.models import PullRef
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.errors import CodeFactoryError
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.tickets.service import TicketService

logger = logging.getLogger(__name__)
PASS_S = float(os.environ.get("CODE_FACTORY_DELIVERY_SECONDS", "10"))
INTAKE_S = 15.0
PASS_LIMIT_S = 300.0


class GitForge:
    """Git's forge and push screen, asked of delivery when used: delivery is built after git."""

    def __init__(self, services: Services) -> None:
        self._services = services

    def _forge(self) -> DeliveryForge:
        return self._services.get(DeliveryForge)

    async def open_pull(
        self, repository: str, *, branch: str, head: str, base: str, title: str
    ) -> PullRef:
        """The pull request of the branch, opened when there is none."""
        return await self._forge().open_pull(
            repository, branch=branch, head=head, base=base, title=title
        )

    async def pull_state(self, ref: PullRef) -> str:
        """GitHub's merge state of the pull request."""
        return await self._forge().pull_state(ref)

    def is_clean(self, state: str) -> bool:
        """Whether the state merges."""
        return self._forge().is_clean(state)

    async def merge(self, ref: PullRef, head: str) -> None:
        """Merge at exactly `head`."""
        await self._forge().merge(ref, head)

    async def held(self, repository: str, branch: str, base: str, new: str) -> str | None:
        """Why the push is held by the screen, or `None`."""
        return await self._forge().held(repository, branch, base, new)


class ChecksForge:
    """The checks module's forge, asked of delivery when used: delivery is built after checks."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def post_commit_status(
        self, repository: str, commit: str, state: str, context: str, description: str
    ) -> bool:
        """Post the commit status; whether GitHub took it."""
        forge = self._services.get(DeliveryForge)
        return await forge.post_status(repository, commit, state, context, description)

    async def open_pull_heads(self, repository: str) -> list[PullHead]:
        """The head of each open pull request delivery recorded for the repository's tickets."""
        return [
            PullHead(repository=pull.repository, ticket_id=pull.ticket_id, head=pull.head)
            for pull in await self._services.get(DeliveryService).open_pulls()
            if pull.repository == repository and pull.head
        ]


_NUMBER = re.compile(r"/pull/(\d+)$")


class DeliveredPulls:
    """Pull requests the board recorded."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def _facts(self) -> list[PullFact]:
        history = await self._services.get(DeliveryService).history()
        per_ticket: dict[str, int] = {}
        for h in history:
            per_ticket[h.pull.ticket_id] = per_ticket.get(h.pull.ticket_id, 0) + 1
        tickets = self._services.get(TicketService)
        facts = []
        for h in history:
            number = _NUMBER.search(h.pull.url)
            title = (await tickets.get(h.pull.ticket_id)).title
            facts.append(
                PullFact(
                    url=h.pull.url,
                    repository=h.pull.repository,
                    number=int(number.group(1)) if number else 0,
                    ticket_id=h.pull.ticket_id,
                    title=title,
                    opened_at=h.opened_at.timestamp(),
                    state=PullState(h.pull.state or "open"),
                    merged_at=h.merged_at.timestamp() if h.merged_at else None,
                    first_review_at=(
                        h.pull.first_review_at.timestamp() if h.pull.first_review_at else None
                    ),
                    changed_lines=(
                        h.pull.additions + h.pull.deletions
                        if h.pull.additions is not None and h.pull.deletions is not None
                        else None
                    ),
                    ticket_pulls=per_ticket[h.pull.ticket_id],
                )
            )
        return facts

    async def opened(self, since: float, until: float) -> list[PullFact]:
        """Pull requests first recorded in `[since, until)`."""
        return [p for p in await self._facts() if since <= p.opened_at < until]

    async def merged(self, since: float, until: float) -> list[PullFact]:
        """Pull requests merged in `[since, until)`."""
        return [
            p
            for p in await self._facts()
            if p.merged_at is not None and since <= p.merged_at < until
        ]


def _event(event: DeliveryEvent) -> ActivityRecord:
    data = event.model_dump(exclude={"id", "ticket_id", "kind", "at"})
    data["retry_at"] = None if event.retry_at is None else event.retry_at.timestamp()
    return ActivityRecord(kind=event.kind, at=event.at.timestamp(), data=data)


class CardDeliveryAdapter:
    """`CardDelivery` over the delivery service's records."""

    def __init__(self, delivery: DeliveryService) -> None:
        self._delivery = delivery

    async def pulls(self, ticket_ids: Sequence[str]) -> dict[str, PullFacts]:
        """The recorded pull request of each ticket that has one."""
        found = await self._delivery.pulls(list(ticket_ids))
        return {i: PullFacts.model_validate(pull.as_card()) for i, pull in found.items()}

    async def events(self, ticket_ids: Sequence[str]) -> dict[str, list[ActivityRecord]]:
        """Each ticket's delivery records, oldest first."""
        found = await self._delivery.events(list(ticket_ids))
        return {i: [_event(e) for e in events] for i, events in found.items()}


def _provide(services: Services, resources: Resources) -> None:
    ports = DeliveryPorts(
        tickets=TicketsAdapter(services),
        git=GitAdapter(services),
        checks=ChecksAdapter(services),
        places=PlacesAdapter(services),
        policy=MergePolicyAdapter(services),
    )
    delivery = DeliveryService(resources.uow, ports)
    services.add(DeliveryService, delivery)
    services.add(DeliveryForge, DeliveryForge(resources.uow, ports))
    services.add(CardDelivery, CardDeliveryAdapter(delivery))


async def _loop(name: str, every: float, work: object) -> None:
    while True:
        try:
            async with asyncio.timeout(PASS_LIMIT_S):
                await work()  # ty: ignore[not-callable]  # a coroutine function
        except (CodeFactoryError, OSError) as error:
            logger.warning("delivery: %s failed: %s", name, error)
        await asyncio.sleep(max(every, 2.0))


def _background(services: Services, tasks: BackgroundTasks) -> None:
    delivery = services.get(DeliveryService)
    tasks.start("delivery-pass", lambda: _loop("pass", PASS_S, delivery.run_pass))
    tasks.start("delivery-intake", lambda: _loop("intake", INTAKE_S, delivery.poll_intake))


module = Module(
    name="delivery",
    provide=_provide,
    commands=(delivery_command,),
    background=_background,
    router=router,
)
