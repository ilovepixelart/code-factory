"""The built-in task of each stage and how a repository's own, the placeholders and the suffixes
reach it. Each named tool must exist and be available to the stage that receives the task."""

import hashlib

import pytest
from mcp_names import tools_named, unknown_tools

from code_factory.agents.rules.fence import digest
from code_factory.agents.rules.tasks import (
    BOARD_SHIPS,
    STAGES,
    built_in_task,
    fill_task,
    plan_first,
    review_guide_note,
    rules_in_use_note,
    stage_instructions,
    stage_task,
)
from code_factory.platform.mcp.policy import TOOLS

OLD_NAME = "whole" + "cycle"  # built from parts: the repository names it nowhere
LIMITS = "Report in at most 8 lines."
# Words in backticks that are skills or document names, not tools.
NOT_TOOLS = {"write_requirements", "make_mock", "write_spec", "write_uat", "build_ticket"}


def test_there_are_five_built_in_stages_and_the_three_review_roles() -> None:
    assert STAGES == ("spec", "build", "review", "critique", "read", "qa", "security", "tests")


def test_an_unknown_stage_gets_builds_task() -> None:
    assert built_in_task("deploy") == built_in_task("build")
    assert built_in_task("") == built_in_task("build")


@pytest.mark.parametrize("stage", ["spec", "build", "review"])
def test_the_working_limits_close_the_tasks_that_change_files(stage: str) -> None:
    assert built_in_task(stage).endswith(LIMITS)


def test_the_spec_task_writes_four_documents_with_write_document() -> None:
    task = built_in_task("spec")
    assert "`write_document`" in task
    for name in ("requirements", "spec", "uat", "mock"):
        assert f"`{name}`" in task
    assert "{id}-R1" in task


def test_spec_and_build_use_the_same_ticket_test_pattern() -> None:
    spec = built_in_task("spec")
    assert "match tests/*" in fill_task(spec, "CF-7", "", "")
    assert "or tests/e2e/* for end-to-end tests" in fill_task(spec, "CF-7", "", "")
    for stage in ("spec", "build"):
        assert "checks/*.py" in fill_task(built_in_task(stage), "CF-7", "checks/*.py", "")


def test_the_review_task_writes_the_review_document_with_severity_and_rule_tags() -> None:
    task = built_in_task("review")
    assert "`review`" in task
    for word in ("[blocker]", "[major]", "[minor]", "[nit]", "[rule: name]", "prior"):
        assert word in task


def test_the_build_task_commits_and_never_pushes_and_may_dismiss_a_finding() -> None:
    task = built_in_task("build")
    assert "{tests}" in task
    assert "Do not push" in task
    assert "`dismiss_finding`" in task


@pytest.mark.parametrize("stage", STAGES)
def test_a_task_names_no_ticket_file_folder_or_old_command(stage: str) -> None:
    task = built_in_task(stage)
    for gone in (
        "{folder}",
        OLD_NAME,
        "review.md",
        "Verdict:",
        "ticket.md",
        ".ticket",
        " save ",
    ):
        assert gone not in task


@pytest.mark.parametrize("stage", STAGES)
def test_every_tool_a_task_names_is_in_the_run_tool_list(stage: str) -> None:
    task = built_in_task(stage)
    allowed = {name for name, rule in TOOLS.items() if rule.run is None or stage in rule.run}
    assert unknown_tools(task, NOT_TOOLS, TOOLS) == set()
    assert tools_named(task, TOOLS) <= allowed


def test_placeholders_are_replaced_by_name_and_defaults_apply_to_empty_patterns() -> None:
    filled = fill_task("{id} {tests} {e2e} {id} {folder} {other}", "CF-7", "", "")
    assert filled == "CF-7 tests/* tests/e2e/* CF-7 {folder} {other}"
    assert fill_task("{tests}|{e2e}", "CF-7", "a/*", "b/*") == "a/*|b/*"


def test_a_ticket_id_holding_a_placeholder_is_not_expanded_again() -> None:
    assert fill_task("{id} {tests}", "{tests}", "x", "") == "{tests} x"


def test_the_repositorys_own_task_replaces_the_built_in_one() -> None:
    assert stage_instructions("My own {id}", "build") == "My own {id}"
    assert stage_instructions("", "build") == built_in_task("build")
    assert stage_instructions("   \n", "review") == built_in_task("review")


def test_the_digest_names_a_task_by_the_first_12_hex_of_its_sha256() -> None:
    assert digest("abc") == hashlib.sha256(b"abc").hexdigest()[:12]
    assert (
        digest(built_in_task("build"))
        == hashlib.sha256(built_in_task("build").encode()).hexdigest()[:12]
    )


def test_a_build_task_gets_the_plan_first_and_the_ship_sentences_in_that_order() -> None:
    plain = stage_task("T", "build")
    assert plain == "T"
    both = stage_task("T", "build", plan=plan_first("CF-3", "plan"), ships=True)
    assert both == f"T\n\n{plan_first('CF-3', 'plan')}\n\n{BOARD_SHIPS}"
    assert "CF-3" in plan_first("CF-3", "plan")
    assert "`write_document`" in plan_first("CF-3", "plan")
    assert "pushes the branch" in BOARD_SHIPS


def test_only_a_review_task_gets_the_rules_in_use_and_the_review_guide() -> None:
    rules = rules_in_use_note(["no-sleeps", "no-mocks"])
    guide = review_guide_note("main", "Be strict.")
    assert rules == (
        "Rule names already in use, most used first (end a finding's item with [rule: name], "
        "reusing one of these when it is the same rule): no-sleeps, no-mocks"
    )
    assert rules_in_use_note([]) == ""
    assert guide.startswith("The repository's review guide (")
    assert guide.endswith("Apply it:\nBe strict.")
    assert stage_task("T", "review", rules=rules, guide=guide) == f"T\n\n{rules}\n\n{guide}"
    assert stage_task("T", "review") == "T"
    assert stage_task("T", "spec", rules=rules, guide=guide, ships=True) == "T"
    assert stage_task("T", "build", rules=rules, guide=guide) == "T"
