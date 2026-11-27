"""Agent runs from the board: starts, stops, holds, logs, usage, previews and permission answers."""

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from code_factory.platform.errors import BadRequestError
from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc
from code_factory.runs.models import PreviewStatus, StartOptions
from code_factory.runs.rules.split import BRIEF_LIMIT, STAGE, split_prompt
from code_factory.runs.service import PermissionService, PreviewService, RunService
from code_factory.tickets.service import TicketService
from code_factory.undo.models import Changed

router = APIRouter(prefix="/api", tags=["runs"])

RunsDep = Annotated[RunService, Depends(service_of(RunService))]
PermissionsDep = Annotated[PermissionService, Depends(service_of(PermissionService))]
PreviewsDep = Annotated[PreviewService, Depends(service_of(PreviewService))]
TicketsDep = Annotated[TicketService, Depends(service_of(TicketService))]
Responses = dict[int | str, dict[str, Any]]
OWNER = "owner:owner"
SAID = {"allow": "Allowed", "deny": "Denied"}
NO_TICKET: Responses = {404: problem_doc("No such ticket.")}
NOTHING = Changed(notice="", undo=None)


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleBody(_Body):
    """A suggested kind of request to adopt as a standing rule."""

    kind: str


class StartBody(_Body):
    """How the run differs from a plain one; both optional, `loop` named as the board's runs."""

    permissions: Literal["acceptEdits", "bypassPermissions"] = "bypassPermissions"
    loop: bool = False

    def options(self) -> StartOptions:
        """The start options this body asks for."""
        return StartOptions(permissions=self.permissions, looping=self.loop)


class Halted(BaseModel):
    """Whether agents are held: when they were, `None` while they may start."""

    halted_at: float | None


def _agents(count: int) -> str:
    return f"{count} agent" if count == 1 else f"{count} agents"


@router.get("/agents", summary="Whether agents are held from starting")
async def halted(runs: RunsDep) -> Halted:
    """`halted_at` in epoch seconds, or null."""
    at = await runs.halted_at()
    return Halted(halted_at=at.timestamp() if at else None)


@router.post("/agents/stop", summary="Stop every agent and hold them until resumed")
async def stop_all(runs: RunsDep) -> Changed:
    """Every active run ends; none starts until `resume`."""
    stopped = await runs.stop_all(OWNER)
    return Changed(
        notice=f"Stopped {_agents(len(stopped))}; agents are held until resumed", undo=None
    )


@router.post("/agents/resume", summary="Let agents start again")
async def resume(runs: RunsDep) -> Changed:
    """A second call changes nothing."""
    await runs.resume()
    return Changed(notice="Agents may start again", undo=None)


@router.post(
    "/runs/{run_id}/stop", summary="Stop one run", responses={404: problem_doc("No such run.")}
)
async def stop(run_id: str, runs: RunsDep) -> Changed:
    """Its process group is ended; the stop is recorded."""
    await runs.stop(run_id)
    return NOTHING


@router.get(
    "/runs/{run_id}/log",
    summary="A run's log, its last mebibyte",
    response_class=PlainTextResponse,
    responses={404: problem_doc("No such run.")},
)
async def log(run_id: str, runs: RunsDep) -> str:
    """Plain text from a line's start; empty before the run writes."""
    return await runs.log(run_id)


@router.get("/usage", summary="Usage per day, agent and model; JSON, or CSV with format=csv")
async def usage(runs: RunsDep, format: Literal["json", "csv"] = "json") -> Response:  # noqa: A002
    """`[{day, agent, model, runs, tokens, cost}]`."""
    if format == "csv":
        return Response(await runs.usage_csv(), media_type="text/csv")
    rows = [row.model_dump(mode="json") for row in await runs.usage()]
    return Response(json.dumps(rows), media_type="application/json")


async def _ticket(tickets: TicketService, repository: str, ticket_id: str) -> str:
    return str((await tickets.locate(repository, ticket_id)).id)


@router.post(
    "/tickets/{repository}/{ticket_id}/runs",
    summary="Start an agent on the ticket's column",
    status_code=201,
    responses=NO_TICKET | {409: problem_doc("The start is refused, with why.")},
)
async def start_run(
    repository: str,
    ticket_id: str,
    runs: RunsDep,
    tickets: TicketsDep,
    body: StartBody | None = None,
) -> Changed:
    """A refusal (held, claimed, no agent, over budget) is a 409 with its sentence."""
    options = (body or StartBody()).options()
    await runs.start(await _ticket(tickets, repository, ticket_id), options=options)
    return NOTHING


class SplitBody(_Body):
    """The brief to split into child tickets of this one."""

    brief: Annotated[str, Field(max_length=BRIEF_LIMIT)]


@router.post(
    "/tickets/{repository}/{ticket_id}/split",
    summary="Split a brief into child tickets",
    status_code=201,
    responses=NO_TICKET
    | {400: problem_doc("No brief."), 409: problem_doc("The start is refused.")},
)
async def split(
    repository: str, ticket_id: str, body: SplitBody, runs: RunsDep, tickets: TicketsDep
) -> Changed:
    """A split run of the ticket: it files the brief's pieces as child tickets as it goes."""
    if not body.brief.strip():
        raise BadRequestError("a split needs a brief")
    found = await tickets.get(await _ticket(tickets, repository, ticket_id))
    prompt = split_prompt(found.id, found.title, found.description, body.brief)
    await runs.start(str(found.id), stage=STAGE, options=StartOptions(prompt=prompt))
    notice = f"Started a split of {found.id}; its tickets appear under it as the run files them"
    return Changed(notice=notice, undo=None)


@router.post(
    "/tickets/{repository}/{ticket_id}/reviews",
    summary="Start a review of the ticket's change",
    status_code=201,
    responses=NO_TICKET | {409: problem_doc("The start is refused, with why.")},
)
async def start_review(
    repository: str, ticket_id: str, runs: RunsDep, tickets: TicketsDep
) -> Changed:
    """A review run reads the change and records its findings."""
    await runs.start(await _ticket(tickets, repository, ticket_id), stage="review")
    return NOTHING


@router.get(
    "/tickets/{repository}/{ticket_id}/preview",
    summary="The ticket's live preview",
    responses=NO_TICKET,
)
async def preview(
    repository: str, ticket_id: str, previews: PreviewsDep, tickets: TicketsDep
) -> PreviewStatus:
    """Whether it is configured and running, its port and address, and how long it idled."""
    return await previews.status(await _ticket(tickets, repository, ticket_id))


@router.post(
    "/tickets/{repository}/{ticket_id}/preview",
    summary="Start the ticket's preview, replacing a running one",
    status_code=201,
    responses=NO_TICKET,
)
async def start_preview(
    repository: str, ticket_id: str, previews: PreviewsDep, tickets: TicketsDep
) -> Changed:
    """The repository's preview command runs in the ticket's worktree."""
    await previews.start(await _ticket(tickets, repository, ticket_id))
    return NOTHING


@router.delete(
    "/tickets/{repository}/{ticket_id}/preview",
    summary="Stop the ticket's preview",
    responses=NO_TICKET,
)
async def stop_preview(
    repository: str, ticket_id: str, previews: PreviewsDep, tickets: TicketsDep
) -> Changed:
    """Stopped, or none ran."""
    await previews.stop(await _ticket(tickets, repository, ticket_id))
    return NOTHING


@router.post(
    "/permissions/rules",
    summary="Adopt a kind of request the owner always allowed as a standing rule",
    responses={409: problem_doc("That is not a suggested rule.")},
)
async def adopt_rule(body: RuleBody, permissions: PermissionsDep) -> Changed:
    """Requests of the kind are allowed from now on without asking."""
    await permissions.adopt_rule(body.kind)
    return Changed(notice=f"Always allowing {body.kind}", undo=None)


@router.post(
    "/permissions/{request_id}/{verdict}",
    summary="Answer an agent's permission request",
    responses={
        404: problem_doc("No such permission request, or its agent stopped waiting."),
        409: problem_doc("Already answered, or older than the wait."),
    },
)
async def answer(
    request_id: str, verdict: Literal["allow", "deny"], permissions: PermissionsDep
) -> Changed:
    """`allow` or `deny`: the waiting agent hears it at once."""
    answered = await permissions.answer(request_id, allow=verdict == "allow", by=OWNER)
    return Changed(notice=f"{SAID[verdict]} {answered.tool} on {answered.ticket_key}", undo=None)
