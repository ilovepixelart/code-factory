"""The Agents page: the roster with what each agent is doing, connections, checks and context."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from code_factory.agents.models.agents import AgentChange
from code_factory.agents.models.answers import Changed
from code_factory.agents.models.connections import ConnectionChange
from code_factory.agents.service import AgentService
from code_factory.platform.web.dependencies import SettingsDep as AppSettingsDep
from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import problem_doc
from code_factory.repositories.service import RepositoryService
from code_factory.settings.models import ConfigUnjudgedError
from code_factory.settings.service import SettingsService
from code_factory.team.service import TeamService

router = APIRouter(prefix="/api", tags=["agents"])

AgentsDep = Annotated[AgentService, Depends(service_of(AgentService))]
TeamDep = Annotated[TeamService, Depends(service_of(TeamService))]
RepositoriesDep = Annotated[RepositoryService, Depends(service_of(RepositoryService))]
SettingsDep = Annotated[SettingsService, Depends(service_of(SettingsService))]
Responses = dict[int | str, dict[str, Any]]
NOT_FOUND: Responses = {404: problem_doc("No agent of that name.")}
REFUSED: Responses = {
    400: problem_doc("The change does not read."),
    409: problem_doc("The change conflicts."),
}


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MoveBody(_Body):
    """Where the agent moves in a column's order."""

    column: str
    direction: str


class RestoreBody(_Body):
    """The saved context to put back, by when it was saved."""

    at: int


class PreviewBody(_Body):
    """Context text to render as the agent page shows it."""

    text: str


class Preview(BaseModel):
    """The context rendered as HTML."""

    html: str


async def _starting(repositories: RepositoryService, settings: SettingsService) -> bool:
    """Whether any tracked repository starts agents on its own (`[agents] slots`)."""
    for record in await repositories.list():
        try:
            config = await settings.load(Path(record.path))
        except ConfigUnjudgedError:
            continue
        if config.agents is not None and (config.agents.slots or 0) > 0:
            return True
    return False


@router.get("/agent-definitions", summary="The roster: agents, runtimes, what each is doing")
async def agent_definitions(
    agents: AgentsDep, team: TeamDep, repositories: RepositoriesDep, settings: SettingsDep
) -> dict[str, Any]:
    """`agents`, `runtimes`, `gaps`, `roles`, `doing`, `last`, `checks`, `starting`, `problem`."""
    listed = (await agents.list_definitions()).wire()
    doing = {name: d.model_dump(mode="json") for name, d in (await team.doing()).items()}
    last = {name: run.model_dump(mode="json") for name, run in (await team.last()).items()}
    return {
        "agents": listed["agents"], "runtimes": listed["runtimes"], "gaps": listed["gaps"],
        "roles": listed["roles"], "doing": doing, "last": last, "checks": listed["checks"],
        "starting": await _starting(repositories, settings), "problem": listed["problem"],
    }  # fmt: skip


@router.get("/harnesses", summary="Check which local agent executables are installed")
async def local_harnesses(agents: AgentsDep, app_settings: AppSettingsDep) -> dict[str, bool]:
    """Availability on the server running Factory. Sign-in and model checks are separate."""
    return await agents.local_harnesses(app_settings.state_dir)


@router.post("/agent-definitions", summary="Define an agent", responses=REFUSED)
async def add_agent(body: AgentChange, agents: AgentsDep) -> Changed:
    """The fields of the new agent; `name` and `runtime` are needed."""
    return await agents.add_agent(body)


@router.patch("/agent-definitions/{name}", summary="Change an agent", responses=NOT_FOUND | REFUSED)
async def edit_agent(name: str, body: AgentChange, agents: AgentsDep) -> Changed:
    """Only the fields given change; a limit set to null clears it."""
    return await agents.edit_agent(name, body)


@router.delete("/agent-definitions/{name}", summary="Remove an agent", responses=NOT_FOUND)
async def remove_agent(name: str, agents: AgentsDep) -> Changed:
    """The answer's undo puts it back."""
    return await agents.remove_agent(name)


@router.post(
    "/agent-definitions/{name}/move", summary="Move an agent in a column", responses=NOT_FOUND
)
async def move_agent(name: str, body: MoveBody, agents: AgentsDep) -> Changed:
    """`direction` is up or down within `column`."""
    return await agents.move_agent(name, body.column, body.direction)


@router.post(
    "/agent-definitions/{name}/context/restore",
    summary="Put back a saved context",
    responses=NOT_FOUND,
)
async def restore_context(name: str, body: RestoreBody, agents: AgentsDep) -> Changed:
    """`at` names the saved version."""
    return await agents.restore_context(name, body.at)


@router.post(
    "/agent-definitions/{name}/model-check",
    summary="Ask the agent's model one short question",
    responses=NOT_FOUND,
)
async def model_check(name: str, agents: AgentsDep) -> dict[str, Any]:
    """Whether its runtime, connection and model answer, and how fast."""
    return (await agents.check_model(name)).wire()


@router.post("/agent-context/preview", summary="Render context text as the page shows it")
async def preview_context(body: PreviewBody, agents: AgentsDep) -> Preview:
    """Markdown rendered as a ticket's description is; raw HTML shows as text."""
    return Preview(html=await agents.preview_context(body.text))


@router.get("/claude-agents", summary="The Claude Code agent files of the tracked repositories")
async def claude_agents(agents: AgentsDep, repositories: RepositoriesDep) -> dict[str, Any]:
    """The agents found, and the files that are not agents with why."""
    roots = [Path(record.path) for record in await repositories.list()]
    return (await agents.claude_agents(roots)).model_dump(mode="json")


@router.get("/connections", summary="The connections agents reach their models through")
async def connections(agents: AgentsDep) -> dict[str, Any]:
    """`connections`, the `kinds` one may add, and `problem`."""
    return (await agents.list_connections()).wire()


@router.post("/connections", summary="Add a connection", responses=REFUSED)
async def add_connection(body: ConnectionChange, agents: AgentsDep) -> Changed:
    """Its name, kind, address and the names of its key variables; never a key itself."""
    return await agents.add_connection(body)


@router.patch("/connections/{name}", summary="Change a connection", responses=REFUSED | NOT_FOUND)
async def edit_connection(name: str, body: ConnectionChange, agents: AgentsDep) -> Changed:
    """Only the fields given change."""
    return await agents.edit_connection(name, body)


@router.delete("/connections/{name}", summary="Remove a connection", responses=NOT_FOUND)
async def remove_connection(name: str, agents: AgentsDep) -> Changed:
    """Refused while an agent uses it."""
    return await agents.remove_connection(name)


@router.get("/connection-status", summary="Whether each connection's keys are set")
async def connection_status(agents: AgentsDep) -> dict[str, Any]:
    """By connection name."""
    return (await agents.connection_status()).wire()
