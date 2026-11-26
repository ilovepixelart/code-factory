"""Admission checks other modules register on the memory service run inside `add` and `propose`.

The contract is the memory-extras spec: the base runs every registered check after its own checks
and before the insert, handing it the draft and who writes it and how.
"""

import pytest

from code_factory.memory.models import Intake, NewMemory
from code_factory.memory.service import MemoryService
from code_factory.platform.errors import BadRequestError, ConflictError
from memory_values import NOW, OWNER

REPO = "sample"
DRAFT = NewMemory(repository=REPO, kind="rule", statement="Keep it small", source="chat")


async def _names(memory: MemoryService) -> list[str]:
    return [entry.id for entry in await memory.list_entries(REPO)]


async def test_an_admission_sees_the_draft_and_how_it_is_written(memory: MemoryService) -> None:
    seen: list[tuple[NewMemory, Intake]] = []

    async def admit(draft: NewMemory, intake: Intake) -> None:
        seen.append((draft, intake))

    memory.add_admission(admit)
    await memory.add(DRAFT, by=OWNER, keep_both=True, check_pairs=True)
    await memory.propose(DRAFT, by="run-1")
    assert [(d.statement, i.model_dump()) for d, i in seen] == [
        (
            "Keep it small",
            {"by": OWNER, "proposed": False, "keep_both": True, "check_pairs": True, "now": NOW},
        ),
        (
            "Keep it small",
            {"by": "run-1", "proposed": True, "keep_both": False, "check_pairs": False, "now": NOW},
        ),
    ]


async def test_a_refusing_admission_leaves_nothing_written(memory: MemoryService) -> None:
    async def admit(draft: NewMemory, intake: Intake) -> None:  # noqa: ARG001
        msg = "it is on the subject of 2026-01-01-x: pass --supersedes or --keep-both"
        raise ConflictError(msg)

    memory.add_admission(admit)
    with pytest.raises(ConflictError, match="on the subject of"):
        await memory.add(DRAFT, by=OWNER)
    with pytest.raises(ConflictError, match="on the subject of"):
        await memory.propose(DRAFT, by="run-1")
    assert await _names(memory) == []


async def test_admissions_run_in_the_order_they_were_registered(memory: MemoryService) -> None:
    order: list[str] = []

    def named(name: str):  # noqa: ANN202
        async def admit(draft: NewMemory, intake: Intake) -> None:  # noqa: ARG001
            order.append(name)

        return admit

    memory.add_admission(named("first"))
    memory.add_admission(named("second"))
    await memory.add(DRAFT, by=OWNER)
    assert order == ["first", "second"]


async def test_the_base_checks_come_before_any_admission(memory: MemoryService) -> None:
    called: list[str] = []

    async def admit(draft: NewMemory, intake: Intake) -> None:  # noqa: ARG001
        called.append(draft.statement)

    memory.add_admission(admit)
    with pytest.raises(BadRequestError, match="an entry needs a source"):
        await memory.add(DRAFT.model_copy(update={"source": ""}), by=OWNER)
    assert called == []


async def test_an_admission_sees_the_cleaned_draft(memory: MemoryService) -> None:
    seen: list[NewMemory] = []

    async def admit(draft: NewMemory, intake: Intake) -> None:  # noqa: ARG001
        seen.append(draft)

    memory.add_admission(admit)
    loose = DRAFT.model_copy(update={"statement": "  Keep it small \n"})
    await memory.add(loose.model_copy(update={"source": " chat "}), by=OWNER)
    await memory.propose(loose.model_copy(update={"source": ""}), by="run-1")
    assert [(d.statement, d.source) for d in seen] == [
        ("Keep it small", "chat"),
        ("Keep it small", "run-1"),
    ]


async def test_a_preparation_runs_first_and_hands_back_the_check_that_runs_in_the_write(
    memory: MemoryService,
) -> None:
    order: list[str] = []

    async def inside(draft: NewMemory, intake: Intake) -> None:  # noqa: ARG001
        order.append("check")

    async def prepare(draft: NewMemory, intake: Intake):  # noqa: ANN202, ARG001
        order.append("prepare")
        return inside

    async def plain(draft: NewMemory, intake: Intake) -> None:  # noqa: ARG001
        order.append("admission")

    memory.add_preparation(prepare)
    memory.add_admission(plain)
    await memory.add(DRAFT, by=OWNER)
    assert order == ["prepare", "admission", "check"]


async def test_a_preparation_that_refuses_leaves_nothing_written(memory: MemoryService) -> None:
    async def prepare(draft: NewMemory, intake: Intake):  # noqa: ANN202, ARG001
        msg = "restates CLAUDE.md line 1: x"
        raise BadRequestError(msg)

    memory.add_preparation(prepare)
    with pytest.raises(BadRequestError, match=r"restates CLAUDE.md line 1"):
        await memory.add(DRAFT, by=OWNER)
    assert await _names(memory) == []
