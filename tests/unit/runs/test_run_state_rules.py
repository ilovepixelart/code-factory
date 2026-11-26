from datetime import UTC, datetime

import pytest

from code_factory.runs.models import Run
from code_factory.runs.rules.records import (
    is_active,
    is_reported,
    is_unfinished,
    state_of,
)

T0 = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def run(**fields: object) -> Run:
    base = {"id": "a1b2c3d4e5f6", "ticket_key": "CF-1", "repository": "sample", "stage": "build"}
    return Run(started_at=T0, **(base | fields))  # ty: ignore[invalid-argument-type]


def test_a_run_with_no_exit_code_is_active() -> None:
    assert is_active(run())
    assert not is_active(run(exit_code=0))


@pytest.mark.parametrize(
    ("fields", "unfinished"),
    [
        ({"exit_code": 0}, False),
        ({"exit_code": 0, "uncommitted": True}, True),
        ({"exit_code": 1}, True),
        ({"exit_code": -15}, True),
        ({"exit_code": 1, "limited_until": T0}, False),
        ({}, False),
    ],
)
def test_unfinished_is_an_ended_run_that_left_work_undone(
    fields: dict[str, object], unfinished: bool
) -> None:
    assert is_unfinished(run(**fields)) is unfinished


def test_a_run_reported_by_a_runner_starts_with_the_runner_prefix() -> None:
    assert is_reported(run(agent="runner:mac"))
    assert not is_reported(run(agent="writer"))


@pytest.mark.parametrize(
    ("fields", "state"),
    [
        ({}, "running"),
        ({"exit_code": 0}, "finished"),
        ({"exit_code": 2}, "failed"),
        ({"exit_code": -15}, "stopped"),
        ({"exit_code": 1, "halted": "stopped at its cap: 5 tokens"}, "stopped"),
        ({"exit_code": 1, "limited_until": T0}, "limited"),
    ],
)
def test_a_run_is_in_one_state(fields: dict[str, object], state: str) -> None:
    assert state_of(run(**fields)) == state
