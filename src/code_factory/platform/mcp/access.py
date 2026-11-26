"""Resolving who is calling, and the guard that keeps a caller to the tools it may use.

Three ways to reach the same server, one policy: over HTTP the bearer token was verified by
FastMCP before the guard runs and its actor travels in the access token's claims; over stdio the
credential is the process's token, verified again on every call so a revoked one stops at once;
in process (tests, an embedding) the actor is fixed and nothing is verified.
"""

from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import override

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import Tool, ToolResult
from mcp import types
from mcp.shared.exceptions import MCPError

from code_factory.platform.errors import CodeFactoryError, ForbiddenError
from code_factory.platform.identity import Actor, ActorVerifier, Role
from code_factory.platform.mcp import policy
from code_factory.platform.mcp.rate import CallRate

ENDED = "forbidden: this token has ended. Start a new run, or ask the owner for a new token."
UNAUTHENTICATED = "forbidden: the request carries no valid token."

_CURRENT: ContextVar[Actor | None] = ContextVar("mcp_actor", default=None)


def current_actor() -> Actor:
    """The actor of the call being served; a tool reads it, the guard sets it."""
    actor = _CURRENT.get()
    if actor is None:
        msg = "no actor: the guard middleware did not run for this call"
        raise RuntimeError(msg)
    return actor


@dataclass(frozen=True)
class Access:
    """How this server learns who is calling.

    Neither `token` nor `actor`: HTTP, where FastMCP verifies the bearer with `verifier`.
    `token`: stdio, the process's credential, verified with `verifier` on every call.
    `actor`: in process, a fixed identity.
    `roles` limits which roles a listener accepts: the runner's address takes run tokens only.
    """

    verifier: ActorVerifier
    token: str | None = None
    actor: Actor | None = None
    roles: frozenset[Role] | None = None  # the roles this listener accepts; `None`: all
    rate: CallRate = field(default_factory=CallRate)

    def __post_init__(self) -> None:
        """Refuse an access that names two ways of identifying the caller."""
        if self.token is not None and self.actor is not None:
            msg = "an access names at most one of a token and an actor"
            raise ValueError(msg)

    @property
    def bearer(self) -> bool:
        """Whether callers present a bearer token with each HTTP request."""
        return self.token is None and self.actor is None

    async def resolve(self) -> Actor:
        """The actor of the current call, or a refusal the model can read."""
        if self.actor is not None:
            return self.actor
        if self.token is not None:
            try:
                actor = await self.verifier.verify_token(self.token)
            except CodeFactoryError as error:  # the database is down: say so, not "internal error"
                raise ToolError(str(error)) from error
            if actor is None:
                raise ToolError(ENDED)
            return actor
        presented = get_access_token()
        if presented is None or "actor" not in presented.claims:
            raise ToolError(UNAUTHENTICATED)
        return Actor.model_validate(presented.claims["actor"])


class Guard(Middleware):
    """Lists only the tools the actor may call and refuses the rest before they run."""

    def __init__(self, access: Access) -> None:
        self._access = access

    @override
    async def on_list_tools(
        self,
        context: MiddlewareContext[types.ListToolsRequest],
        call_next: CallNext[types.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        """The tools of the server that the caller's role and stage allow, in the server's order."""
        try:
            actor = await self._access.resolve()
        except ToolError as refused:  # a listing is not a tool call: a protocol error carries it
            raise MCPError(types.INVALID_REQUEST, str(refused)) from refused
        tools = await call_next(context)
        allowed = set(policy.visible(actor, (tool.name for tool in tools)))
        order = {name: place for place, name in enumerate(policy.TOOLS)}
        shown = [tool for tool in tools if tool.name in allowed]
        return sorted(shown, key=lambda tool: order[tool.name])

    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[types.CallToolRequestParams],
        call_next: CallNext[types.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Refuse a tool the actor may not call; otherwise run it with the actor set."""
        actor = await self._access.resolve()
        name = context.message.name
        if not policy.may_call(actor, name):
            error: ForbiddenError = policy.refuse_tool(actor, name)
            raise ToolError(str(error))
        waited = self._access.rate.wait(str(actor.token_id))
        if waited is not None:
            raise ToolError(self._access.rate.refusal(waited))
        token = _CURRENT.set(actor)
        try:
            return await call_next(context)
        finally:
            _CURRENT.reset(token)
