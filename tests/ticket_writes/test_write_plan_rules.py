"""Plans of a create and an update: what they write, in which order they refuse.

Expected values: the golden answers G[0] to G[23] (their sentences and activity), the previous
implementation's `ticket_fields.rs` cases and hand-worked orders.
"""

from collections.abc import Callable

from code_factory.ticket_writes.models import CreatePlan, Record, UpdatePlan
from code_factory.ticket_writes.rules import (
    branch_missing,
    held_text,
    plan_create,
    plan_update,
    with_question,
    written_fields,
)
from code_factory.tickets.models import NewTicket, TicketCore
from write_values import core, graph, no_branch_refusal

GRAPH = graph(1, 2, 3)


def create(
    fields: dict[str, str], refuse: Callable[[str], str | None] = no_branch_refusal
) -> CreatePlan | str:
    return plan_create("sample", fields, GRAPH, refuse)


def update(
    current: TicketCore,
    patch: dict[str, str],
    refuse: Callable[[str], str | None] = no_branch_refusal,
) -> UpdatePlan | str:
    return plan_update(current, patch, GRAPH, refuse)


def test_a_create_strips_normalises_and_records_the_type() -> None:
    plan = create(
        {
            "title": "  New thing ",
            "type": "bug",
            "labels": "a, b,",
            "priority": "high",
            "due": "2026-11-01",
        }
    )
    assert plan == CreatePlan(
        ticket=NewTicket(
            repository="sample",
            title="New thing",
            type="bug",
            labels=["a", "b"],
            priority="high",
            due="2026-11-01",
        ),
        branch="",
        archived=False,
        activity=[Record(kind="created", data={"type": "bug"})],
    )


def test_a_create_without_a_type_is_a_feature() -> None:
    plan = create({"title": "Plain"})
    assert isinstance(plan, CreatePlan)
    assert plan.ticket.type == "feature"
    assert plan.activity == [Record(kind="created", data={"type": "feature"})]


def test_a_create_keeps_a_blank_title_for_the_tickets_module_to_judge() -> None:
    plan = create({"title": "   "})
    assert isinstance(plan, CreatePlan)
    assert plan.ticket.title == ""


def test_a_create_takes_links_and_documents() -> None:
    plan = create(
        {
            "title": "T",
            "blocked_by": " CF-1 ,, CF-3",
            "parent": "CF-2",
            "caused_by": "CF-1",
            "pages": "a, b",
            "tests": "t",
            "e2e": "e",
            "parallel": "02",
            "budget": ".5",
            "source": "https://x/1",
            "branch": " feat/x ",
            "archived": "on",
        }
    )
    assert isinstance(plan, CreatePlan)
    ticket = plan.ticket
    assert (ticket.blocked_by, ticket.parent, ticket.caused_by) == (
        ["CF-1", "CF-3"],
        "CF-2",
        ["CF-1"],
    )
    assert (ticket.pages, ticket.tests, ticket.e2e, ticket.parallel, ticket.budget) == (
        "a, b",
        "t",
        "e",
        "2",
        "0.5",
    )
    assert (ticket.source, plan.branch, plan.archived) == ("https://x/1", "feat/x", True)


def test_a_create_refuses_in_the_order_of_the_previous_store() -> None:
    every = {
        "title": "T",
        "type": "epic",
        "stage": "later",
        "priority": "soon",
        "branch": "bad name",
        "budget": "abc",
        "parallel": "9",
        "parent": "CF-9",
    }
    expected = [
        ("type", "unknown type epic"),
        ("stage", "unknown stage later"),
        ("priority", "unknown priority soon"),
        ("branch", "bad branch bad name: no spaces"),
        ("budget", "budget must be a number of dollars"),
        ("parallel", "parallel must be 1 to 4"),
        ("parent", "no ticket CF-9"),
    ]
    seen = []
    fields = dict(every)
    for name, _sentence in expected:
        seen.append((name, create(fields, lambda _n: "no spaces")))
        del fields[name]
    assert seen == [(n, s) for n, s in expected]


def test_a_line_break_is_refused_before_every_other_check() -> None:
    assert create({"title": "a\nb", "type": "epic"}) == "title holds a line break"


def test_an_update_refuses_unknown_fields_first() -> None:
    assert update(core(2), {"nope": "x", "title": "a\nb"}) == "unknown fields ['nope']"


def test_an_update_refuses_a_blank_title() -> None:
    assert update(core(2), {"title": "  "}) == "a ticket needs a title"


def test_an_update_refuses_an_unknown_type_and_an_unknown_non_empty_stage() -> None:
    assert update(core(2), {"type": "epic"}) == "unknown type epic"
    assert update(core(2), {"stage": "later"}) == "unknown stage later"
    plan = update(core(2), {"stage": ""})
    assert isinstance(plan, UpdatePlan)
    assert plan.stage == ""


def test_an_update_names_only_the_fields_that_differ_in_the_order_given() -> None:
    current = core(2, title="Same", priority="low")
    plan = update(current, {"title": "Same", "priority": "high", "labels": "x, y", "assignee": ""})
    assert isinstance(plan, UpdatePlan)
    assert plan.values == {"priority": "high", "labels": "x, y"}
    assert plan.activity == [
        Record(kind="field", data={"name": "priority", "value": "high"}),
        Record(kind="field", data={"name": "labels", "value": "x, y"}),
    ]
    assert plan.changed == ["priority", "labels"]


def test_an_update_that_changes_nothing_writes_nothing() -> None:
    plan = update(
        core(2, labels=["a", "b"], blocked_by=["CF-1"]), {"labels": "a,b", "blocked_by": "CF-1"}
    )
    assert plan == UpdatePlan(values={}, stage="", archived=None, activity=[])


def test_a_description_is_recorded_without_its_text() -> None:
    plan = update(core(2), {"description": "A longer story.\n"})
    assert isinstance(plan, UpdatePlan)
    assert plan.values == {"description": "A longer story."}
    assert plan.activity == [Record(kind="field", data={"name": "description", "value": ""})]


def test_archiving_records_after_the_fields_and_never_as_a_field() -> None:
    plan = update(core(2), {"archived": "true", "title": "New"})
    assert isinstance(plan, UpdatePlan)
    assert plan.values == {"title": "New"}
    assert plan.archived is True
    assert plan.activity == [
        Record(kind="field", data={"name": "title", "value": "New"}),
        Record(kind="archived", data={}),
    ]
    assert plan.changed == ["title", "archived"]


def test_restoring_records_restored_and_archiving_an_archived_ticket_is_no_change() -> None:
    restored = update(core(2, archived=True), {"archived": ""})
    assert isinstance(restored, UpdatePlan)
    assert (restored.archived, restored.activity) == (False, [Record(kind="restored", data={})])
    same = update(core(2, archived=True), {"archived": "on"})
    assert isinstance(same, UpdatePlan)
    assert (same.archived, same.activity) == (None, [])


def test_a_stage_is_carried_not_recorded() -> None:
    plan = update(core(2), {"stage": "spec", "labels": "x, y"})
    assert isinstance(plan, UpdatePlan)
    assert plan.stage == "spec"
    assert plan.values == {"labels": "x, y"}
    assert plan.activity == [Record(kind="field", data={"name": "labels", "value": "x, y"})]


def test_a_branch_is_checked_only_when_it_differs() -> None:
    seen: list[str] = []

    def refuse(name: str) -> str | None:
        seen.append(name)
        return "no"

    same = update(core(2, branch="feat/x"), {"branch": "feat/x"}, refuse)
    assert same == UpdatePlan(values={}, stage="", archived=None, activity=[])
    assert seen == []
    assert update(core(2, branch="feat/x"), {"branch": "feat/y"}, refuse) == "bad branch feat/y: no"
    assert seen == ["feat/y"]


def test_an_update_checks_links_it_adds_and_not_the_ones_held() -> None:
    assert update(core(2), {"blocked_by": "CF-2"}) == "CF-2 cannot link to itself"
    assert update(core(2), {"blocked_by": "CF-9"}) == "no ticket CF-9"
    held = update(core(2, blocked_by=["CF-9"]), {"blocked_by": "CF-9, CF-1"})
    assert isinstance(held, UpdatePlan)
    assert held.values == {"blocked_by": "CF-9, CF-1"}


def test_an_update_refuses_a_parent_that_leads_back() -> None:
    loop = plan_update(core(1), {"parent": "CF-3"}, graph(1, 3, parents={3: 1}), no_branch_refusal)
    assert loop == "parent CF-3 would make a loop"


def test_the_blocker_list_is_normalised_in_the_value_and_the_record() -> None:
    plan = update(core(2), {"blocked_by": " CF-1 ,, CF-3"})
    assert isinstance(plan, UpdatePlan)
    assert plan.values == {"blocked_by": "CF-1, CF-3"}
    assert plan.activity == [
        Record(kind="field", data={"name": "blocked_by", "value": "CF-1, CF-3"})
    ]


def test_an_update_refuses_with_the_golden_sentences() -> None:
    assert update(core(2), {"budget": "abc"}) == "budget must be a number of dollars"
    assert update(core(2), {"priority": "soon"}) == "unknown priority soon"
    assert update(core(2), {"archived": "maybe"}) == "bad archived maybe"
    assert update(core(2), {"due": "2026-13-01"}) == "bad due date 2026-13-01"
    assert update(core(2), {"parallel": "7"}) == "parallel must be 1 to 4"


def test_held_text_shows_each_field_as_the_app_does() -> None:
    ticket = core(2, labels=["a", "b"], blocked_by=["CF-1", "CF-3"], archived=True, rank=4)
    assert [
        held_text(ticket, n) for n in ("labels", "blocked_by", "archived", "title", "rank")
    ] == [
        "a, b",
        "CF-1, CF-3",
        "true",
        "T2",
        "4",
    ]
    assert held_text(core(2), "archived") == ""


def test_written_fields_split_the_lists_and_keep_the_text() -> None:
    assert written_fields({"labels": "a, b", "blocked_by": "", "title": "T", "parent": "CF-1"}) == {
        "labels": ["a", "b"],
        "blocked_by": [],
        "title": "T",
        "parent": "CF-1",
    }


def test_a_branch_no_ref_holds_is_refused_with_how_to_make_one() -> None:
    assert branch_missing("feat/x", {"main"}, {"dev"}, "main") == (
        "no branch feat/x exists, so the ticket would stay in Spec: code-factory start <ID> "
        "or a Build run makes the ticket's branch from main; set branch once it exists"
    )


def test_a_branch_a_local_or_remote_ref_holds_passes() -> None:
    assert branch_missing("feat/x", {"feat/x"}, set(), "main") is None
    assert branch_missing("feat/x", set(), {"feat/x"}, "main") is None


def test_a_duplicate_question_follows_the_description_after_a_blank_line() -> None:
    assert with_question("Plan.\n", "Is this CF-3?") == "Plan.\n\nIs this CF-3?"
    assert with_question("", "Is this CF-3?") == "Is this CF-3?"
    assert with_question("  \n", "Is this CF-3?") == "Is this CF-3?"


def test_a_link_list_naming_a_ticket_twice_changes_nothing_when_it_already_holds_it() -> None:
    plan = update(core(2, blocked_by=["CF-1"]), {"blocked_by": "CF-1, CF-1"})
    assert plan == UpdatePlan(values={}, stage="", archived=None, activity=[])


def test_a_create_files_in_the_guarded_repository_whatever_the_fields_name() -> None:
    plan = create({"title": "Moved", "repository": "elsewhere"})

    assert isinstance(plan, CreatePlan)
    assert plan.ticket.repository == "sample"
