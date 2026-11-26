import pytest

from code_factory.runs.rules.process import (
    elapsed_seconds,
    exit_status,
    same_process,
    signal_group,
    wrapper_status,
)


@pytest.mark.parametrize("pid", [1, 0, -1, -4242, 2**31, 2**31 + 7])
def test_no_group_at_or_below_pid_one_or_past_the_pid_range_is_signalled(pid: int) -> None:
    assert signal_group(pid) is None


@pytest.mark.parametrize("pid", [2, 4242, 2**31 - 1])
def test_a_pid_inside_the_range_names_its_group(pid: int) -> None:
    assert signal_group(pid) == pid


@pytest.mark.parametrize(
    ("etime", "seconds"),
    [("05:07", 307), ("1:02:03", 3723), ("2-03:04:05", 183845), ("00:00", 0)],
)
def test_elapsed_time_of_ps_is_read_in_seconds(etime: str, seconds: int) -> None:
    assert elapsed_seconds(etime) == seconds


@pytest.mark.parametrize("junk", ["", "a:b", "12", "1:2:3:4", "-1:00", "1-"])
def test_elapsed_time_that_is_not_ps_output_is_none(junk: str) -> None:
    assert elapsed_seconds(junk) is None


@pytest.mark.parametrize(("skew", "same"), [(0.0, True), (2.0, True), (-2.0, True), (3.0, False)])
def test_a_process_is_the_recorded_one_within_two_seconds_of_start(skew: float, same: bool) -> None:
    command = "/bin/sh -c wrapper /state/runs/ab12.exit -- claude"
    assert same_process(1000.0 + skew, 1000.0, command, "ab12.exit") is same


def test_a_process_running_another_command_is_not_the_recorded_one() -> None:
    assert not same_process(1000.0, 1000.0, "/bin/sleep 100", "ab12.exit")


def test_a_process_that_is_gone_is_not_the_recorded_one() -> None:
    assert not same_process(None, 1000.0, "", "ab12.exit")


def test_a_signal_death_is_reported_negative_and_a_normal_exit_as_it_is() -> None:
    assert exit_status(-15) == -15
    assert exit_status(0) == 0
    assert exit_status(3) == 3


def test_the_wrapper_exits_128_minus_the_signal_for_a_negative_code() -> None:
    assert wrapper_status(-15) == 143
    assert wrapper_status(0) == 0
    assert wrapper_status(7) == 7
