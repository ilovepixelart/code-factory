"""After a tool result: what the owner said on the ticket since the session last heard."""

from typing import Any

from pydantic import ValidationError

from code_factory.hooks.models import TellAnswer, TellConfirm
from code_factory.hooks.rules import output
from code_factory.hooks.rules.tell import eligible
from code_factory.hooks.service.base import Collaborators
from code_factory.platform.errors import BadRequestError
from code_factory.platform.identity import Actor

MALFORMED = "confirm is malformed"


class TellMixin(Collaborators):
    """News for a running session, and the confirmation that it was given."""

    async def tell(self, actor: Actor, payload: dict[str, Any]) -> TellAnswer:
        """The hook text and the marks to confirm it with; nothing is marked here.

        Empty unless the event is a tool's result of a session, the actor is a run on a ticket and
        the ticket has news since the run started.
        """
        event, session = payload.get("hook_event_name"), payload.get("session_id")
        if not (isinstance(event, str) and isinstance(session, str) and eligible(event, session)):
            return TellAnswer()
        if actor.ticket_id is None or actor.run_id is None:
            return TellAnswer()
        started = await self._ports.runs.started(actor.run_id)
        if started is None:
            return TellAnswer()
        news = await self._ports.talk.peek(actor.ticket_id, session, started)
        if news is None:
            return TellAnswer()
        return TellAnswer(output=output.tell(event, news.text), confirm=news.confirm)

    async def confirm_tell(self, actor: Actor, session_id: str, confirm: dict[str, Any]) -> None:
        """Mark what the session was given as delivered.

        `BadRequestError` for marks of a wrong shape or no session; an actor with no ticket marks
        nothing.
        """
        try:
            marks = TellConfirm.model_validate(confirm)
        except ValidationError as error:
            raise BadRequestError(MALFORMED) from error
        if not session_id:
            raise BadRequestError(MALFORMED)
        if actor.ticket_id is not None:
            await self._ports.talk.confirm(actor.ticket_id, session_id, marks)
