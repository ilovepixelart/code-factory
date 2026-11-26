"""The tool list is the product surface: its shape is pinned, and the rules every tool follows."""

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client

from code_factory.memory.module import module as memory_module
from code_factory.memory.service import MemoryService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.mcp import Access, build_mcp, policy
from code_factory.platform.mcp.scope import TicketRepositories
from code_factory.platform.services import Services
from code_factory.talk.module import module as talk_module
from code_factory.talk.service import TalkService
from code_factory.tickets.module import module as tickets_module
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)
from mcp_support import OWNER, NoTokens, run_actor
from repo_files import ROOT

GOLDEN = ROOT / "tests" / "golden" / "mcp"
BLESS = "CODE_FACTORY_BLESS"
VERBS = {
    "get", "list", "create", "update", "post", "read", "write", "submit", "dismiss",
    "search", "propose", "ask", "answer", "start", "stop", "run", "whoami",
}  # fmt: skip
DESCRIPTION_LIMIT = 600
# Bytes a build run's tool list costs on every connection: what the model reads (descriptions and
# input schemas) and the whole list with the output schemas.
RUN_MODEL_LIMIT = 15_000
RUN_LIST_LIMIT = 24_000


@pytest.fixture
def services(uow: UnitOfWork) -> Services:
    registry = Services()
    for key, service in (
        (TicketService, TicketService(uow)),
        (TicketRepositories, TicketService(uow)),
        (ActivityService, ActivityService(uow)),
        (DocumentService, DocumentService(uow)),
        (ReviewService, ReviewService(uow)),
        (MemoryService, MemoryService(uow)),
        (TalkService, TalkService(uow)),
    ):
        registry.add(key, service)
    return registry


async def _listed(services: Services, actor: object) -> list[dict[str, Any]]:
    access = Access(verifier=NoTokens(), actor=actor)  # ty: ignore[invalid-argument-type]
    server = build_mcp(services, [tickets_module, talk_module, memory_module], access=access)
    async with Client(server) as client:
        tools = await client.list_tools()
    keys = ("name", "description", "inputSchema", "outputSchema", "annotations")
    return [
        {
            key: value
            for key, value in tool.model_dump(mode="json", by_alias=True, exclude_none=True).items()
            if key in keys
        }
        for tool in tools
    ]


def _check_golden(name: str, listed: list[dict[str, Any]]) -> None:
    path = GOLDEN / f"{name}.json"
    text = json.dumps(listed, indent=2, sort_keys=True) + "\n"
    if os.environ.get(BLESS) == "1":
        path.write_text(text, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == text, (
        f"the tool list for {name} changed: read the diff, and bless it with {BLESS}=1 if intended"
    )


async def test_the_owners_tool_list_is_the_pinned_one(services: Services) -> None:
    _check_golden("tools.owner", await _listed(services, OWNER))


async def test_a_build_runs_tool_list_is_the_pinned_one(services: Services) -> None:
    _check_golden("tools.run-build", await _listed(services, run_actor("build", "CF-1")))


async def test_every_listed_tool_is_in_the_access_table_in_its_order(services: Services) -> None:
    names = [tool["name"] for tool in await _listed(services, OWNER)]
    assert names == [name for name in policy.TOOLS if name in names]
    assert set(names) <= set(policy.TOOLS)


async def test_each_actor_lists_exactly_the_tools_the_table_allows_it(services: Services) -> None:
    built: set[str] = set()
    for actor in (OWNER, run_actor("review", "CF-1"), run_actor("build", "CF-1")):
        built |= {tool["name"] for tool in await _listed(services, actor)}
    every = [name for name in policy.TOOLS if name in built]
    for actor in (
        run_actor("spec", "CF-1"),
        run_actor("build", "CF-1"),
        run_actor("coordinate", None),
    ):
        listed = [tool["name"] for tool in await _listed(services, actor)]
        assert listed == policy.visible(actor, every)


async def test_every_tool_states_all_four_hints(services: Services) -> None:
    for tool in await _listed(services, OWNER):
        hints = tool["annotations"]
        wanted = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
        assert wanted <= set(hints), tool["name"]


async def test_a_tool_that_reads_changes_nothing_and_a_tool_that_writes_is_not_read_only(
    services: Services,
) -> None:
    reads = {
        "whoami",
        "get_ticket",
        "list_tickets",
        "list_questions",
        "list_activity",
        "read_document",
        "search_memory",
    }
    for tool in await _listed(services, OWNER):
        assert tool["annotations"]["readOnlyHint"] is (tool["name"] in reads), tool["name"]


async def test_every_description_says_when_to_use_the_tool_and_stays_short(
    services: Services,
) -> None:
    for tool in await _listed(services, OWNER):
        text = tool["description"]
        assert re.search(r"\bUse (when|to|first|before)\b", text), tool["name"]
        assert len(text) <= DESCRIPTION_LIMIT, (tool["name"], len(text))


async def test_names_are_verb_noun_inputs_refuse_extras_and_outputs_are_objects(
    services: Services,
) -> None:
    for tool in await _listed(services, OWNER):
        assert re.fullmatch(r"[a-z]+(_[a-z]+)*", tool["name"]), tool["name"]
        assert tool["name"].split("_")[0] in VERBS, tool["name"]
        assert tool["inputSchema"].get("additionalProperties") is False, tool["name"]
        assert tool["outputSchema"]["type"] == "object", tool["name"]


async def test_the_list_a_build_run_reads_on_every_connection_stays_small(
    services: Services,
) -> None:
    listed = await _listed(services, run_actor("build", "CF-1"))
    read_by_the_model = [{k: v for k, v in t.items() if k != "outputSchema"} for t in listed]
    assert len(json.dumps(read_by_the_model)) <= RUN_MODEL_LIMIT
    assert len(json.dumps(listed)) <= RUN_LIST_LIMIT


def test_the_golden_folder_holds_only_the_pinned_lists() -> None:
    assert sorted(path.name for path in Path(GOLDEN).iterdir()) == [
        "tools.owner.json",
        "tools.run-build.json",
    ]
