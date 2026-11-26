"""The memory tools through the MCP client, over the real service and the test database."""

import asyncio

import pytest

from code_factory.memory.models import NewMemory
from code_factory.memory.module import module as memory_module
from code_factory.memory.service import MemoryService
from code_factory.platform.services import Services
from mcp_support import OWNER, call, run_actor


@pytest.fixture
def services(memory: MemoryService) -> Services:
    registry = Services()
    registry.add(MemoryService, memory)
    return registry


async def _seed(memory: MemoryService, statement: str, repository: str = "sample") -> str:
    entry = await memory.add(
        NewMemory(repository=repository, kind="rule", statement=statement, source="owner"),
        by="owner:test",
    )
    return entry.id


async def test_a_run_finds_the_active_rules_of_its_repository_whose_words_all_match(
    services: Services, memory: MemoryService
) -> None:
    kept = await _seed(memory, "Measure before changing a read path")
    await _seed(memory, "Measure twice elsewhere", repository="elsewhere")
    await _seed(memory, "Name tests for behaviour")
    run = run_actor("build", "CF-1")
    found = await call(services, [memory_module], run, "search_memory", query="measure PATH")
    assert [row["id"] for row in found.data["items"]] == [kept]
    assert found.data["items"][0]["statement"] == "Measure before changing a read path"
    everything = await call(services, [memory_module], run, "search_memory")
    assert len(everything.data["items"]) == 2


async def test_a_run_reads_active_entries_only_and_the_owner_reads_proposals(
    services: Services,
) -> None:
    run = run_actor("build", "CF-1")
    proposed = await call(
        services, [memory_module], run, "propose_memory", statement="Pin the clock"
    )
    refused = await call(services, [memory_module], run, "search_memory", status="proposed")
    assert refused.text == "forbidden: a run reads active memory only. Leave status as it is."
    seen = await call(
        services, [memory_module], OWNER, "search_memory", status="proposed", repository="sample"
    )
    assert [row["id"] for row in seen.data["items"]] == [proposed.data["id"]]
    hidden = await call(services, [memory_module], run, "search_memory", query="clock")
    assert hidden.data["items"] == []


async def test_a_run_proposes_a_lesson_held_for_approval_up_to_five(
    services: Services, memory: MemoryService
) -> None:
    run = run_actor("build", "CF-1")
    for number in range(5):
        made = await call(
            services,
            [memory_module],
            run,
            "propose_memory",
            statement=f"Lesson number {number} about clocks",
            why="A flaky test",
            cites=["tests/a.py"],
        )
        assert (made.ok, made.data["status"]) == (True, "proposed")
    entry = await memory.get("sample", made.data["id"])
    assert (entry.proposed, entry.why, entry.cites, entry.source) == (
        True,
        "A flaky test",
        ["tests/a.py"],
        "run:r1",
    )
    sixth = await call(
        services, [memory_module], run, "propose_memory", statement="One lesson too many"
    )
    assert (sixth.ok, sixth.text) == (
        False,
        "limit: 5 memory proposals already made by this run. Put the rest in notes.",
    )


async def test_the_owner_proposes_without_a_limit_but_names_the_repository(
    services: Services,
) -> None:
    missing = await call(services, [memory_module], OWNER, "propose_memory", statement="x y z")
    assert missing.text.startswith("repository is required")
    for number in range(6):
        made = await call(
            services,
            [memory_module],
            OWNER,
            "propose_memory",
            statement=f"Owner lesson {number} on logging",
            repository="sample",
        )
        assert made.ok


async def test_a_long_statement_is_cut_and_says_so(
    services: Services, memory: MemoryService
) -> None:
    await _seed(memory, "word " * 400)
    found = await call(
        services, [memory_module], run_actor("build", "CF-1"), "search_memory", query="word"
    )
    row = found.data["items"][0]
    assert (len(row["statement"]), row["truncated"]) == (1500, True)


async def test_a_run_reads_and_proposes_only_in_its_own_repository(
    services: Services, memory: MemoryService
) -> None:
    await _seed(memory, "Measure twice elsewhere", repository="elsewhere")
    run = run_actor("build", "CF-1")
    expected = (
        "out_of_scope: this token is scoped to repository sample; elsewhere is not available to it."
    )
    searched = await call(services, [memory_module], run, "search_memory", repository="elsewhere")
    proposed = await call(
        services,
        [memory_module],
        run,
        "propose_memory",
        statement="A lesson",
        repository="elsewhere",
    )
    assert (searched.text, proposed.text) == (expected, expected)
    owner = await call(services, [memory_module], OWNER, "search_memory", repository="elsewhere")
    assert len(owner.data["items"]) == 1


async def test_two_proposals_at_once_with_one_slot_left_make_one(services: Services) -> None:
    run = run_actor("build", "CF-1")
    for number in range(4):
        await call(
            services, [memory_module], run, "propose_memory", statement=f"Lesson {number} on clocks"
        )
    answers = await asyncio.gather(
        *(
            call(services, [memory_module], run, "propose_memory", statement=f"Racing lesson {n}")
            for n in range(2)
        )
    )
    assert sorted(a.ok for a in answers) == [False, True]


async def test_entries_of_the_same_day_and_name_page_in_repository_order(
    services: Services, memory: MemoryService
) -> None:
    await _seed(memory, "Pin the clock", repository="zeta")
    await _seed(memory, "Pin the clock", repository="alpha")
    first = await call(services, [memory_module], OWNER, "search_memory", limit=1)
    second = await call(
        services, [memory_module], OWNER, "search_memory", limit=1, cursor=first.data["next_cursor"]
    )
    assert [first.data["items"][0]["repository"], second.data["items"][0]["repository"]] == [
        "alpha",
        "zeta",
    ]
