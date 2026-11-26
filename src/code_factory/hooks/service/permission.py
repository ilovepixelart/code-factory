"""A run's permission request: settled by the permission service, the hook held open meanwhile."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import anyio

from code_factory.hooks.rules import output
from code_factory.hooks.service.base import CLEANUP_S, Collaborators
from code_factory.platform.identity import Actor

logger = logging.getLogger(__name__)

TREE_EDIT = "an edit inside the run's tree"
STANDING = "a standing rule of the owner"


def _behavior(answer: dict[str, Any]) -> str:
    decision = answer.get("hookSpecificOutput", {}).get("decision", {})
    return str(decision.get("behavior", "")) if isinstance(decision, dict) else ""


class PermissionMixin(Collaborators):
    """The permission hook and the codex client's question."""

    async def permission(
        self,
        actor: Actor,
        payload: dict[str, Any],
        *,
        sandboxed: bool,
        alive: Callable[[], Awaitable[bool]],
    ) -> str | None:
        """The hook text for a request, or `None` to print nothing.

        Nothing for an actor with no ticket and when the hook closed (`alive` turned false: the
        request is withdrawn). A request nobody answers in the wait gets the words that tell the
        run to do it another way. Each answer is recorded on the ticket; a failure to record is
        logged and the run still hears the answer.
        """
        if actor.ticket_id is None or actor.run_id is None:
            return None
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            answer = await self._answered(actor.run_id, payload, sandboxed, alive)
        except TimeoutError:
            text, behavior = output.permission("deny", output.UNANSWERED), "deny"
        else:
            if answer is None:
                return None
            text, behavior = output.rendered(answer), _behavior(answer)
        await self._record(actor.ticket_id, payload, behavior, int(loop.time() - started))
        return text

    async def codex_allows(self, actor: Actor, payload: dict[str, Any], *, in_tree: bool) -> bool:
        """Whether a codex run's request is allowed.

        An edit in its tree, then a standing rule, then the permission path of a claude run; true
        only for an allow.
        """
        if actor.ticket_id is None or actor.run_id is None:
            return False
        permissions = self._ports.permissions
        tool = str(payload.get("tool_name", ""))
        if in_tree:
            await permissions.record(actor.run_id, tool, allow=True, by="policy", reason=TREE_EDIT)
            return True
        kind = permissions.kind(tool, payload.get("tool_input"))
        if kind is not None and kind in await permissions.rules():
            await permissions.record(actor.run_id, tool, allow=True, by="owner", reason=STANDING)
            return True

        async def open_connection() -> bool:
            return True

        said = await self.permission(actor, payload, sandboxed=False, alive=open_connection)
        return said is not None and '"behavior": "allow"' in said

    async def _answered(
        self,
        run_id: str,
        payload: dict[str, Any],
        sandboxed: bool,
        alive: Callable[[], Awaitable[bool]],
    ) -> dict[str, Any] | None:
        """The service's answer; `None` when the hook closed, `TimeoutError` past the wait."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._wait_s
        request = asyncio.create_task(
            self._ports.permissions.request(run_id, payload, sandboxed=sandboxed, wait=self._wait_s)
        )
        try:
            while True:
                left = deadline - loop.time()
                if left <= 0:
                    raise TimeoutError
                done, _ = await asyncio.wait({request}, timeout=min(self._poll_s, left))
                if done:
                    return request.result()
                if not await self._open(alive):
                    return None
        finally:
            await self._stop(request)

    @staticmethod
    async def _open(alive: Callable[[], Awaitable[bool]]) -> bool:
        try:
            return await alive()
        except Exception:
            logger.debug("could not tell whether the hook is still there", exc_info=True)
            return True

    @staticmethod
    async def _stop(request: asyncio.Task[dict[str, Any]]) -> None:
        """End a request still running and wait for it to withdraw itself, cancelled or not."""
        if not request.done():
            request.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.wait({request}, timeout=CLEANUP_S)
        if request.done() and not request.cancelled():
            request.exception()  # retrieved: a failure past the answer is not lost to the loop

    async def _record(
        self, ticket_id: str, payload: dict[str, Any], behavior: str, waited: int
    ) -> None:
        data: dict[str, object] = {
            "tool": str(payload.get("tool_name", "")),
            "decision": behavior,
            "waited": waited,
        }
        try:
            await self._ports.tickets.record(ticket_id, "permission", data, "board")
        except Exception:
            logger.warning(
                "could not record the permission decision on %s", ticket_id, exc_info=True
            )
