"""Bearer verification for the HTTP transport: FastMCP asks, the auth module answers."""

from typing import override

from fastmcp.server.auth import AccessToken, TokenVerifier

from code_factory.platform.identity import ActorVerifier, Role


class ActorTokenVerifier(TokenVerifier):
    """Accepts a bearer token the actor verifier knows; FastMCP answers 401 for any other."""

    def __init__(self, verifier: ActorVerifier, roles: frozenset[Role] | None = None) -> None:
        super().__init__()
        self._verifier = verifier
        self._roles = roles

    @override
    async def verify_token(self, token: str) -> AccessToken | None:
        """The access token carrying the actor, or `None`."""
        actor = await self._verifier.verify_token(token)
        if actor is None or (self._roles is not None and actor.role not in self._roles):
            return None
        return AccessToken(
            token=token,
            client_id=actor.subject,
            scopes=[actor.role.value],
            expires_at=int(actor.expires_at.timestamp()),
            claims={"actor": actor.model_dump(mode="json")},
        )
