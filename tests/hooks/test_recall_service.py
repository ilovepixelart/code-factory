"""What a session is handed back at its start: the ticket it works on, its rules, within the cap."""

import pytest

from code_factory.hooks.ports import Checkout, MemoryContext, MemoryRecall
from code_factory.platform.errors import NotFoundError
from hooks_fakes import OWNER_ACTOR, TICKET, Fakes, run_actor

HEADING = "code-factory: read again at the start of this session."
MEMORY_HEADING = "Standing rules, decisions and lessons, each with why:"
TICKET_LINE = "Ticket on this branch: CF-5 Work (stage: build, branch ticket/cf-5)"


def remembering() -> Fakes:
    fakes = Fakes()
    fakes.memory.recall_given = MemoryRecall(
        kept=[("m1", "- Run the tests Why: they catch drift")],
        left=[("m2", "- Old lesson Why: long ago")],
        index=["- m9: Archived thing"],
    )
    return fakes


async def test_a_run_is_handed_its_memory_its_ticket_and_the_archive_index() -> None:
    fakes = remembering()
    fakes.tickets.rows = ["CF-5-R1: It does the thing"]

    recalled = await fakes.service().recall(cwd="/anywhere", actor=run_actor(), session_id="s-1")

    assert recalled is not None
    assert recalled.text == (
        f"{HEADING}\n{MEMORY_HEADING}\n- Run the tests Why: they catch drift\n"
        "Left out over the memory budget of 8,000 characters (read them with the search_memory "
        "tool): Old lesson\n"
        f"{TICKET_LINE}\nRequirements:\nCF-5-R1: It does the thing\n"
        "Archived memory, not loaded: read one with the search_memory tool (id: title):\n"
        "- m9: Archived thing\n"
    )
    assert (recalled.memory_kept, recalled.ticket_kept) == (1, 3)


async def test_a_run_gets_the_context_of_its_ticket_and_records_what_it_received() -> None:
    fakes = remembering()
    fakes.checkouts.paths = ["web/src/a.vue", "src/b.py"]

    await fakes.service().recall(cwd="/anywhere", actor=run_actor(), session_id="s-1")

    assert fakes.memory.asked == [
        (
            "sample",
            MemoryContext(stage="build", paths=["web/src/a.vue", "src/b.py"], labels=["ui"]),
            "CF-5",
            "r-1",
        )
    ]
    assert fakes.checkouts.asked == []


async def test_an_owner_session_finds_its_ticket_by_the_branch_of_its_folder() -> None:
    fakes = remembering()
    fakes.checkouts.found = Checkout(repository="sample", branch="ticket/cf-5")
    fakes.tickets.branches[("sample", "ticket/cf-5")] = TICKET

    recalled = await fakes.service().recall(cwd="/r/tree", actor=OWNER_ACTOR, session_id="")

    assert recalled is not None
    assert TICKET_LINE in recalled.text
    assert fakes.checkouts.asked == ["/r/tree"]
    assert fakes.memory.asked[0][2:] == ("CF-5", None)


async def test_a_session_in_a_repository_on_a_branch_with_no_ticket_gets_the_memory_only() -> None:
    fakes = remembering()
    fakes.checkouts.found = Checkout(repository="sample", branch="main")

    recalled = await fakes.service().recall(cwd="/r", actor=None, session_id="")

    assert recalled is not None
    assert "Ticket on this branch" not in recalled.text
    assert fakes.memory.asked == [("sample", MemoryContext(), None, None)]


async def test_a_folder_outside_every_repository_is_nothing_and_never_an_error() -> None:
    fakes = remembering()

    assert (
        await fakes.service().recall(cwd="/elsewhere/x", actor=OWNER_ACTOR, session_id="") is None
    )
    assert await fakes.service().recall(cwd="/elsewhere/x", actor=None, session_id="") is None
    assert fakes.memory.asked == []


async def test_nothing_to_say_is_nothing() -> None:
    fakes = Fakes()
    fakes.checkouts.found = Checkout(repository="sample", branch="main")

    assert await fakes.service().recall(cwd="/r", actor=None, session_id="") is None


async def test_a_ticket_alone_is_something_to_say() -> None:
    fakes = Fakes()

    recalled = await fakes.service().recall(cwd="/r", actor=run_actor(), session_id="s")

    assert recalled is not None
    assert recalled.text == f"{HEADING}\n{TICKET_LINE}\n"


async def test_a_coordinator_run_has_no_ticket_and_records_no_delivery() -> None:
    fakes = remembering()

    await fakes.service().recall(
        cwd="/r", actor=run_actor(ticket_id=None, stage=None), session_id="s"
    )

    assert fakes.memory.asked == [("sample", MemoryContext(), None, None)]


async def test_a_run_whose_ticket_is_gone_is_not_found() -> None:
    fakes = remembering()
    fakes.tickets.tickets.clear()

    with pytest.raises(NotFoundError):
        await fakes.service().recall(cwd="/r", actor=run_actor(), session_id="s")


async def test_four_hundred_requirements_stay_within_the_cap_and_say_what_was_left_out() -> None:
    fakes = remembering()
    fakes.memory.recall_given = MemoryRecall(
        kept=[(f"m{n}", f"- Rule {n} " + "x" * 1_000) for n in range(1, 10)],
        overflow="The rules and decisions above take 500 characters over the memory budget.",
    )
    fakes.tickets.rows = [
        f"CF-5-R{n}: Requirement number {n} reads like a long sentence" for n in range(1, 401)
    ]

    recalled = await fakes.service().recall(cwd="/r", actor=run_actor(), session_id="s")

    assert recalled is not None
    lines = recalled.text.splitlines()
    assert len(recalled.text) <= 10_000
    assert lines[2].endswith("9 entries")
    assert lines[3] == TICKET_LINE
