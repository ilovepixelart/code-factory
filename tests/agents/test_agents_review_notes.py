"""What a repository's config adds to a run's task: review roles, guardrails, the code map."""

from code_factory.agents.rules.codemap import code_map
from code_factory.agents.rules.tasks import (
    REVIEW_ROLES,
    built_in_task,
    guardrail_note,
    role_notes,
    stage_task,
)


def test_the_review_is_told_which_roles_ran_before_it_and_to_carry_their_findings() -> None:
    assert role_notes(["security", "nope", "qa"]) == (
        "Before this review, the security, qa review ran as runs of their own and recorded "
        "their findings as notes in the ticket's activity. Read them with `list_activity`: carry "
        "each that still holds on this diff into the `review` document as a finding of yours "
        "with its severity, rule and note_id from the activity; leave out one the diff disproves."
    )
    assert role_notes(["nope"]) == ""


def test_each_role_runs_its_checklist_records_notes_and_changes_no_file() -> None:
    for role, checklist in REVIEW_ROLES.items():
        task = built_in_task(role)
        assert task.startswith(checklist)
        assert "`post_note`" in task
        assert "Change no file" in task
        assert "`write_document`" not in task


def test_every_role_tags_its_findings_with_its_rule() -> None:
    assert {name: "[rule: " in text for name, text in REVIEW_ROLES.items()} == {
        "qa": True,
        "security": True,
        "tests": True,
    }


def test_the_guardrails_name_the_paths_and_the_size_and_send_a_crossing_back() -> None:
    assert guardrail_note(["migrations/**", "*.lock"], 400) == (
        "The repository's guardrails: a change to a path matching migrations/**, *.lock; more "
        "than 400 changed lines. When the diff crosses one and the ticket's requirements do not "
        "ask for it, raise a [blocker] finding ending [rule: guardrail], which sends the change "
        "back to Build."
    )
    assert guardrail_note([], None) == ""


def test_roles_reach_a_review_task_and_no_other() -> None:
    assert stage_task("Review.", "review", roles="As QA.") == "Review.\n\nAs QA."
    assert stage_task("Build.", "build", roles="As QA.") == "Build."


def test_the_code_map_lists_files_by_folder_with_counts() -> None:
    files = ["README.md", "src/a.py", "src/b.py", "src/pkg/c.py"]

    assert code_map(files) == (
        "Code map (tracked files by folder; read a file before relying on it):\n"
        "- . (1): README.md\n"
        "- src/ (2): a.py, b.py\n"
        "- src/pkg/ (1): c.py"
    )


def test_a_long_folder_and_a_long_map_are_cut_and_say_what_they_left_out() -> None:
    crowded = code_map([f"f{n:02}.py" for n in range(14)])
    many = code_map([f"d{n}/x.py" for n in range(5)], limit=3)

    assert crowded.endswith("f11.py, +2 more")
    assert many.splitlines()[-1] == "... 3 more folders"
    assert code_map([]) == ""
