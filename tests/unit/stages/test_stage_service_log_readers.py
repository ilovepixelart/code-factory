"""The readers of a checks log that the checks module calls through the stage service."""

from code_factory.stages.service import StageService


def test_a_kill_code_with_no_failed_step_line_is_a_killed_run() -> None:
    assert StageService.killed_run(137, "gate: vite-build starts\ntransforming...\n")


def test_a_kill_code_after_a_failed_step_line_is_a_failure_not_a_kill() -> None:
    log = "gate: lint failed (exit 1) after 3s\n"
    assert not StageService.killed_run(137, log)


def test_an_ordinary_failure_code_is_not_a_killed_run() -> None:
    assert not StageService.killed_run(1, "gate: lint starts\n")


def test_the_last_started_step_is_the_one_a_killed_run_was_in() -> None:
    log = "gate: preflight starts\ngate: preflight passed in 1s\ngate: web-unit starts\n"
    assert StageService.last_started_step(log) == "web-unit"
    assert StageService.last_started_step("no gate here\n") is None
