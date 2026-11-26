"""The container's name and turn, and the heavy-step lock's text and moves."""

import pytest

from code_factory.checks.rules import (
    HeavyMove,
    board_text,
    container_name,
    counts_as_holder,
    docker_never_started,
    holder_name,
    holder_pid,
    named_container,
    next_move,
    next_turn,
    plain,
    wait_bound,
)


def test_a_container_is_named_for_its_check() -> None:
    assert container_name(42) == "code-factory-check-42"


def test_the_name_goes_in_right_after_the_removal_flag() -> None:
    argv = ["docker", "run", "--rm", "--network", "none", "img", "/bin/sh", "-c", "true"]
    assert named_container(argv, "code-factory-check-7") == [
        "docker",
        "run",
        "--rm",
        "--name",
        "code-factory-check-7",
        "--network",
        "none",
        "img",
        "/bin/sh",
        "-c",
        "true",
    ]


def test_a_command_line_without_the_removal_flag_is_refused() -> None:
    with pytest.raises(ValueError, match="--rm"):
        named_container(["docker", "run", "img"], "n")


def test_a_daemon_error_with_no_step_started_means_the_container_never_started() -> None:
    assert docker_never_started("docker: Error response from daemon: no such image\n")
    assert docker_never_started("docker: Cannot connect to the Docker daemon at unix:///x\n")


def test_a_step_that_started_means_the_container_did_start() -> None:
    log = "gate: preflight starts\ndocker: Error response from daemon: gone\n"
    assert not docker_never_started(log)
    assert not docker_never_started("gate: lint starts\n")
    assert not docker_never_started("just output\n")


@pytest.mark.parametrize(
    ("queued", "running", "slots", "expected"),
    [
        ([3], 0, 1, 3),
        ([3], 1, 1, None),
        ([3], 1, 2, 3),
        ([], 0, 1, None),
        ([9, 4, 7], 0, 1, 4),
        ([5], 0, 0, 5),  # zero slots read as one
        ([5], 1, 0, None),
    ],
)
def test_the_oldest_queued_id_takes_a_slot_when_one_is_free(
    queued: list[int], running: int, slots: int, expected: int | None
) -> None:
    assert next_turn(queued, running, slots) == expected


SECOND = 1.0


def test_the_wait_bound_is_whole_seconds_or_1800() -> None:
    assert wait_bound(None) == 1800
    assert wait_bound("") == 1800
    assert wait_bound("0") == 0
    assert wait_bound("45") == 45
    assert wait_bound("-5") == 1800
    assert wait_bound("4x") == 1800


def test_the_boards_lock_names_its_pid_step_and_tree() -> None:
    assert board_text(4242, "/trees/CF-9") == "4242 container in /trees/CF-9 on the board"


def test_a_holder_is_the_leading_number_of_the_text() -> None:
    assert holder_pid("25705 rust-test in /trees/CF-9 on b") == 25705
    assert holder_pid("x25 rust-test in /t on b") is None
    assert holder_pid(" 25 rust-test") is None
    assert holder_pid("") is None


def test_a_holder_is_named_without_control_characters() -> None:
    assert (
        holder_name("25705 rust-test in /trees/CF-9 on ticket/cf-9")
        == "pid 25705: rust-test in /trees/CF-9 on ticket/cf-9"
    )
    assert plain("a\x1b[31mb\nc") == "a[31mbc"


def test_a_gate_and_the_board_count_as_holders_and_another_process_does_not() -> None:
    gate = "7 rust-test in /t on b"
    board = "7 container in /t on the board"
    assert counts_as_holder(gate, "sh scripts/gate.sh --reached")
    assert not counts_as_holder(gate, "/usr/bin/vim notes")
    assert counts_as_holder(board, "/usr/local/bin/code-factory serve")
    assert not counts_as_holder("7 container-x in /t on b", "/usr/bin/vim")
    assert counts_as_holder(gate, None)


def test_a_waiter_releases_a_gone_holder_and_takes_over_a_non_gate() -> None:
    held = "7 rust-test in /t on b"
    gone = next_move(held, running=False, counts=True, waited=1, bound=10)
    assert gone == HeavyMove(
        "release",
        "released the heavy-step lock of pid 7: rust-test in /t on b; that process is gone",
    )
    other = next_move(held, running=True, counts=False, waited=1, bound=10)
    assert other == HeavyMove(
        "release",
        "took over the heavy-step lock of pid 7: rust-test in /t on b; that process is no gate",
    )


def test_a_waiter_waits_until_the_bound_and_then_goes_on() -> None:
    held = "7 rust-test in /t on b"
    assert next_move(held, running=True, counts=True, waited=9.9, bound=10) == HeavyMove("wait")
    assert next_move(held, running=True, counts=True, waited=10, bound=10) == HeavyMove(
        "go_on",
        "runs without the heavy-step lock: held over 10s, now by pid 7: rust-test in /t on b",
    )
