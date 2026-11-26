"""Build waits for its spec, and a broken default branch or a revert files a bug."""

from datetime import UTC, datetime, timedelta

from code_factory.follower.models import Card
from code_factory.follower.rules import plan_queue
from code_factory.follower.rules.filing import main_failure_fields, recurring_due, revert_fields
from code_factory.follower.rules.queue import reader_due, roles_due, spec_hold
from code_factory.team.rules.pick import judging

GAPS = ("spec has no ## Blast radius section",)


def _card(**change: object) -> Card:
    return Card.model_validate({"id": "CF-1", "repository": "r", "stage": "build", **change})


def test_a_build_whose_spec_is_not_ready_waits_with_the_gap_named() -> None:
    plan = plan_queue([_card(build_gaps=GAPS)], [], slots={"r": 1}, overall=None, limits={})

    assert [(p.id, p.reason) for p in plan] == [
        ("CF-1", "spec not ready: spec has no ## Blast radius section")
    ]


def test_a_build_with_a_ready_spec_starts() -> None:
    plan = plan_queue([_card()], [], slots={"r": 1}, overall=None, limits={})

    assert [(p.id, p.reason) for p in plan] == [("CF-1", "")]


def test_a_fix_a_review_and_a_spec_run_never_wait_on_the_spec() -> None:
    assert [
        spec_hold(_card(build_gaps=GAPS, fix_due=True)),
        spec_hold(_card(build_gaps=GAPS, stage="review", review_due=True)),
        spec_hold(_card(build_gaps=GAPS, stage="spec")),
    ] == ["", "", ""]


def test_a_broken_default_branch_files_one_bug_named_by_the_commit_that_broke_it() -> None:
    fields = main_failure_fields(
        repository="shop",
        commit="abcdef1234",
        step="lint",
        broken_by="9876543210",
        passed="1111111",
        ticket="CF-7",
    )

    assert fields == {
        "title": "shop: main fails lint at abcdef1",
        "type": "bug",
        "description": (
            "The default branch's own checks fail lint at abcdef1234. Broken by 9876543. "
            "Fix it before more work merges on top."
        ),
        "source": "main:9876543210",
        "caused_by": ["CF-7"],
    }


def test_later_commits_on_a_branch_still_broken_name_the_same_breakage() -> None:
    first = main_failure_fields(
        repository="r", commit="aaa", step="", broken_by="", passed="ppp", ticket=""
    )
    later = main_failure_fields(
        repository="r", commit="bbb", step="", broken_by="", passed="ppp", ticket=""
    )

    assert (first["source"], later["source"], "caused_by" in first) == (
        "main:after ppp",
        "main:after ppp",
        False,
    )


def test_a_reverted_merge_files_a_bug_caused_by_its_ticket() -> None:
    assert revert_fields("Gift cards", "ticket/cf-3", "CF-3") == {
        "title": "Reverted: Gift cards",
        "type": "bug",
        "description": (
            "The merge of CF-3 was reverted on the default branch. Find why it did not hold, "
            "and land it again with a test that would have caught it."
        ),
        "source": "revert:ticket/cf-3",
        "caused_by": ["CF-3"],
    }


def test_a_recurring_entry_of_no_ticket_type_files_nothing_and_one_without_a_type_files() -> None:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    entries = [
        {"title": "Chore", "every": "month", "type": "chore"},
        {"title": "Plain", "every": "month"},
    ]

    assert recurring_due(entries, set(), now) == [
        {"title": "Plain", "source": "recurring:Plain@2026-09"}
    ]


BUILT = datetime(2026, 9, 1, 12, tzinfo=UTC)


def test_every_role_is_due_before_the_first_review_in_the_configured_order() -> None:
    runs = [("build", BUILT, True)]

    assert roles_due(["security", "qa"], runs) == ["security", "qa"]


def test_a_role_that_succeeded_since_the_build_is_done_and_a_failed_one_is_due_again() -> None:
    later = BUILT + timedelta(minutes=5)
    runs = [("build", BUILT, True), ("qa", later, True), ("security", later, False)]

    assert roles_due(["qa", "security"], runs) == ["security"]


def test_a_new_build_makes_every_role_due_again() -> None:
    runs = [
        ("build", BUILT, True),
        ("qa", BUILT + timedelta(minutes=5), True),
        ("build", BUILT + timedelta(minutes=10), True),
    ]

    assert roles_due(["qa"], runs) == ["qa"]
    assert roles_due([], runs) == []


def test_a_review_role_is_taken_by_the_review_column_and_never_by_the_builds_writer() -> None:
    assert [judging(role) for role in ("qa", "security", "tests")] == [("review", "build")] * 3


def test_the_spec_reader_runs_after_the_spec_and_before_the_first_build() -> None:
    spec = [("spec", BUILT, True)]
    read = [*spec, ("read", BUILT + timedelta(minutes=5), True)]
    failed = [*spec, ("read", BUILT + timedelta(minutes=5), False)]

    assert [
        reader_due(spec, spec_reader=True, plan_critic=False),
        reader_due(read, spec_reader=True, plan_critic=False),
        reader_due(failed, spec_reader=True, plan_critic=False),
        reader_due(spec, spec_reader=False, plan_critic=False),
    ] == ["read", "", "read", ""]


def test_a_spec_rewritten_after_its_read_is_read_again() -> None:
    runs = [
        ("spec", BUILT, True),
        ("read", BUILT + timedelta(minutes=5), True),
        ("spec", BUILT + timedelta(minutes=10), True),
    ]

    assert reader_due(runs, spec_reader=True, plan_critic=False) == "read"


def test_the_plan_critic_runs_once_after_a_build_and_never_before_one() -> None:
    built = [("spec", BUILT, True), ("build", BUILT + timedelta(minutes=5), False)]
    critiqued = [*built, ("critique", BUILT + timedelta(minutes=9), True)]

    assert [
        reader_due(built, spec_reader=True, plan_critic=True),
        reader_due(critiqued, spec_reader=True, plan_critic=True),
        reader_due([("spec", BUILT, True)], spec_reader=False, plan_critic=True),
        reader_due(built, spec_reader=False, plan_critic=False),
    ] == ["critique", "", "", ""]


def test_the_spec_reader_is_taken_by_the_spec_column_but_never_by_its_writer() -> None:
    assert (judging("read"), judging("critique")) == (("spec", "spec"), ("review", "build"))
