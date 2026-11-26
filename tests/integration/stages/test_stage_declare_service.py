"""Declaring a column exactly: no refusal, an empty name clears (what an undo of a move needs)."""

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.stages.service import StageService
from code_factory.tickets.models import Ticket
from code_factory.tickets.service import ActivityService
from stage_fakes import FakeFacts
from ticket_values import OWNER


async def last_stage_record(activity: ActivityService, ticket: str) -> dict[str, object]:
    page = await activity.list_activity(ticket, kinds=["stage"], newest_first=True, limit=1)
    return dict(page.items[0].data)


async def test_declare_pins_exactly_the_column_and_records_where_the_card_came_from(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    moved = await stages.declare(started.id, "spec", OWNER)

    assert (moved.from_stage, moved.to_stage) == ("build", "spec")
    assert (moved.declared_before, moved.declared_after, moved.changed) == ("", "spec", True)
    assert (await stages.assess(started.id)).declared == "spec"
    assert await last_stage_record(activity, started.id) == {"from": "build", "to": "spec"}


async def test_declare_names_a_column_even_where_a_move_would_be_refused(
    stages: StageService, started: Ticket
) -> None:
    moved = await stages.declare(started.id, "review", OWNER)

    assert (moved.to_stage, moved.declared_after) == ("review", "review")
    assert (await stages.assess(started.id)).stage == "review"


async def test_declaring_the_column_the_evidence_reached_still_pins_it(
    stages: StageService, started: Ticket
) -> None:
    moved = await stages.declare(started.id, "build", OWNER)

    assert (moved.declared_after, moved.changed) == ("build", True)
    assert (await stages.assess(started.id)).declared == "build"


async def test_an_empty_name_clears_the_pin_and_the_card_follows_its_evidence_again(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    await stages.declare(started.id, "spec", OWNER)

    cleared = await stages.declare(started.id, "", OWNER)

    assert (cleared.declared_before, cleared.declared_after, cleared.changed) == ("spec", "", True)
    assert (await stages.assess(started.id)).stage == "build"
    assert await last_stage_record(activity, started.id) == {"from": "spec", "to": "build"}


async def test_declaring_what_is_declared_changes_and_records_nothing(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    await stages.declare(started.id, "spec", OWNER)
    before = (await activity.list_activity(started.id, kinds=["stage"])).items

    again = await stages.declare(started.id, "spec", OWNER)

    assert (again.declared_before, again.declared_after, again.changed) == ("spec", "spec", False)
    assert (await activity.list_activity(started.id, kinds=["stage"])).items == before


@pytest.mark.parametrize("name", ["later", "released", "Spec"])
async def test_a_name_that_is_no_board_column_is_refused(
    stages: StageService, started: Ticket, name: str
) -> None:
    with pytest.raises(BadRequestError, match=f"unknown stage {name}"):
        await stages.declare(started.id, name, OWNER)
    assert (await stages.assess(started.id)).declared == ""


async def test_declaring_for_a_missing_ticket_is_not_found(stages: StageService) -> None:
    with pytest.raises(NotFoundError, match="CF-999999"):
        await stages.declare("CF-999999", "spec", OWNER)


async def test_declaring_needs_no_readable_git(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()
    facts.answers.clear()
    await stages.observe()
    assert (await stages.assess(started.id)).git_unreadable is True

    moved = await stages.declare(started.id, "spec", OWNER)

    assert (moved.declared_after, moved.changed) == ("spec", True)
    assert (await stages.assess(started.id)).declared == "spec"


async def test_declare_that_expects_the_held_column_writes_it(
    stages: StageService, started: Ticket
) -> None:
    await stages.declare(started.id, "spec", OWNER)

    moved = await stages.declare(started.id, "review", OWNER, expect="spec")

    assert (moved.declared_before, moved.declared_after) == ("spec", "review")
    assert (await stages.assess(started.id)).declared == "review"


@pytest.mark.parametrize(
    ("held", "expect", "target"),
    [
        ("review", "spec", "build"),
        ("review", "", "build"),
        ("", "spec", "build"),
        ("review", "spec", ""),
        ("review", "", ""),
    ],
)
async def test_declare_that_expects_another_column_conflicts_and_writes_nothing(
    stages: StageService, started: Ticket, held: str, expect: str, target: str
) -> None:
    if held:
        await stages.declare(started.id, held, OWNER)

    with pytest.raises(ConflictError, match=f"^{started.id} stage changed since it was read$"):
        await stages.declare(started.id, target, OWNER, expect=expect)

    assert (await stages.assess(started.id)).declared == held


async def test_declare_that_expects_no_declaration_pins_the_column(
    stages: StageService, started: Ticket
) -> None:
    await stages.declare(started.id, "spec", OWNER, expect="")

    assert (await stages.assess(started.id)).declared == "spec"


async def test_declare_that_expects_none_and_clears_none_changes_nothing(
    stages: StageService, started: Ticket
) -> None:
    moved = await stages.declare(started.id, "", OWNER, expect="")

    assert moved.changed is False
