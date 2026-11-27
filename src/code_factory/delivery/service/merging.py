"""The board merge: every guard on the same head, then `gh pr merge --match-head-commit`."""

import asyncio
import json

from code_factory.delivery.models import (
    LiveRead,
    Merged,
    MergeFacts,
    MergeRefusedError,
    MergeVerdict,
    NotReadyError,
    PullView,
)
from code_factory.delivery.rules import attempts, merge_decision, merge_due, next_retry
from code_factory.delivery.service.base import Collaborators, logger
from code_factory.platform.errors import CodeFactoryError, NotFoundError, UnavailableError

LIVE_FIELDS = "state,baseRefName,headRefOid,mergeStateStatus,isDraft"
NO_TICKET = "no such ticket"


class MergingMixin(Collaborators):
    """Merging a ticket's pull request."""

    async def _live(self, repository: str, url: str) -> LiveRead:
        answer = await self._gh_in(repository, ["pr", "view", url, "--json", LIVE_FIELDS])
        if not answer.ok:
            return LiveRead(state="", base="", head="", merge_state="", base_error=answer.reason)
        data = json.loads(answer.stdout or "{}")
        return LiveRead(
            state=str(data.get("state") or ""),
            base=str(data.get("baseRefName") or ""),
            head=str(data.get("headRefOid") or ""),
            merge_state=str(data.get("mergeStateStatus") or ""),
            draft=data.get("isDraft") is True,
        )

    async def _facts(self, ticket_id: str, *, live: bool) -> MergeFacts:
        ticket = await self._ports.tickets.get(ticket_id)
        repository = ticket.repository
        pull = await self._pull_of(ticket_id)
        configured = await self._ports.checks.configured(repository)
        checked = "missing"
        if pull is not None and pull.head:
            checked = await self._ports.checks.verdict(repository, ticket_id, pull.head)
        read = await self._live(repository, pull.url) if live and pull and pull.url else None
        return MergeFacts(
            pull=pull,
            default_branch=await self._ports.git.default_branch(repository),
            checks_configured=configured,
            checked=checked if checked in {"passed", "failed"} else "missing",
            events=tuple(await self._events_of(ticket_id)),
            live=read,
        )

    async def why(self, ticket_id: str) -> MergeVerdict:
        """The merge rule's verdict now, with a live read of the pull request."""
        return merge_decision(await self._facts(ticket_id, live=True))

    def owner_hold(self, ticket_id: str, head: str) -> str:
        """The last unattended merge check's owner hold, for this exact head."""
        held_head, reason = self._owner_holds.get(ticket_id, ("", ""))
        return reason if held_head == head else ""

    async def _check_automatic_policy(self, ticket_id: str, head: str) -> None:
        hold = await self._ports.policy.automatic_hold(ticket_id, head)
        if hold is not None and hold.owner:
            self._owner_holds[ticket_id] = (head, hold.reason)
        else:
            self._owner_holds.pop(ticket_id, None)
        if hold is not None:
            raise NotReadyError(hold.reason)

    async def merge(self, ticket_id: str, by: str = "") -> Merged:
        """Merge the ticket's pull request when every guard holds; `NotReadyError` otherwise.

        An owner call (`by` set) can resolve an unattended hold and skips the retry wait.
        """
        lock = self._merging.setdefault(ticket_id, asyncio.Lock())
        async with lock:
            return await self._merge(ticket_id, by)

    async def _merge(self, ticket_id: str, by: str) -> Merged:
        facts = await self._facts(ticket_id, live=True)
        pull = facts.pull
        if pull is None:
            raise NotReadyError(merge_decision(facts).reason or NO_TICKET)
        if not by and not merge_due(facts, self._clock()):
            raise NotReadyError("a failed merge of this head waits before it is tried again")
        verdict = merge_decision(facts)
        if not verdict.ready:
            self._owner_holds.pop(ticket_id, None)
            if verdict.record_base_unread:
                await self._record(
                    self._event(
                        ticket_id,
                        "merge_base_unread",
                        url=pull.url,
                        head=pull.head,
                        reason=verdict.reason,
                    )
                )
            raise NotReadyError(verdict.reason)
        if not by:
            await self._check_automatic_policy(ticket_id, pull.shipped_head)
        repository = pull.repository
        try:
            answer = await self._gh_in(repository, list(verdict.argv))
        except UnavailableError:
            answer = None
        if answer is None or not answer.ok:
            if await self._merged_meanwhile(ticket_id, repository, pull.url):
                return await self._done(ticket_id, pull, by)
            reason = answer.reason if answer else "gh did not answer"
            count = attempts(facts.events, "merge_failed", pull.shipped_head)
            await self._record(
                self._event(
                    ticket_id,
                    "merge_failed",
                    url=pull.url,
                    head=pull.shipped_head,
                    reason=reason,
                    by=by,
                    retry_at=next_retry(count, reason, self._clock()),
                )
            )
            raise MergeRefusedError(f"GitHub refused the merge: {reason}")
        return await self._done(ticket_id, pull, by)

    async def _merged_meanwhile(self, ticket_id: str, repository: str, url: str) -> bool:
        read = await self._read_pull(ticket_id, repository, url)
        return read is not None and read.state == "merged"

    async def _done(self, ticket_id: str, pull: PullView, by: str) -> Merged:
        url, head = pull.url, pull.shipped_head
        self._owner_holds.pop(ticket_id, None)
        await self._record(self._event(ticket_id, "merged_pull_request", url=url, head=head, by=by))
        await self._ports.tickets.record_pull(ticket_id, url, "merged")
        await self._ports.tickets.record_merged(ticket_id)
        try:
            await self._ports.git.catch_up(pull.repository)
        except CodeFactoryError as error:
            logger.warning("delivery: origin of %s not fetched: %s", pull.repository, error)
        return Merged(url=url, head=head)

    async def merge_finished(self) -> list[str]:
        """Merge every open pull request whose repository does not wait for the owner."""
        merged: list[str] = []
        pulls = await self._open_pulls()
        open_ids = {pull.ticket_id for pull in pulls}
        self._owner_holds = {i: held for i, held in self._owner_holds.items() if i in open_ids}
        for pull in pulls:
            switches = await self._ports.places.switches(pull.repository)
            if switches.merge_waits or not pull.shipped_head:
                continue
            try:
                await self.merge(pull.ticket_id)
            except (NotReadyError, MergeRefusedError, NotFoundError) as refused:
                logger.debug("delivery: %s not merged: %s", pull.ticket_id, refused)
                continue
            merged.append(pull.ticket_id)
        return merged
