"""Who may call which tool, and what a run may touch: the matrix is written out by hand here."""

from datetime import UTC, datetime

import pytest

from code_factory.platform.errors import BadRequestError, ForbiddenError
from code_factory.platform.identity import Actor, Role
from code_factory.platform.mcp import policy
from repo_files import ROOT

EXPIRES = datetime(2026, 12, 1, tzinfo=UTC)


def _run(stage: str, ticket: str | None = "CF-12") -> Actor:
    role = Role.RUN if ticket is not None else Role.COORDINATOR
    return Actor(
        role=role, subject="run:r1", token_id=1, run_id="r1", ticket_id=ticket, stage=stage,
        repository="/r", expires_at=EXPIRES,
    )  # fmt: skip


OWNER = Actor(role=Role.OWNER, subject="owner:alex", token_id=2, expires_at=EXPIRES)
COORDINATOR = _run("coordinate", ticket=None)

EVERY_RUN = ["spec", "build", "review", "split"]
# The review roles and the second readers read and record notes; they write no document and file
# no ticket.
ROLES = ["qa", "security", "tests", "read", "critique"]
READERS = [*EVERY_RUN, *ROLES]

# tool -> (roles that may call it, run stages that may). Taken from the table in the MCP design.
EXPECTED: dict[str, tuple[set[Role], list[str]]] = {
    "whoami": ({Role.RUN, Role.COORDINATOR, Role.OWNER}, [*READERS, "judge"]),
    "get_ticket": ({Role.RUN, Role.COORDINATOR, Role.OWNER}, READERS),
    "list_tickets": ({Role.COORDINATOR, Role.OWNER}, []),
    "create_ticket": ({Role.RUN, Role.COORDINATOR, Role.OWNER}, EVERY_RUN),
    "update_ticket": ({Role.OWNER}, []),
    "list_activity": ({Role.RUN, Role.COORDINATOR, Role.OWNER}, READERS),
    "post_note": ({Role.RUN, Role.COORDINATOR, Role.OWNER}, READERS),
    "get_qa_holdout": ({Role.RUN}, ["qa"]),
    "read_document": ({Role.RUN, Role.OWNER}, READERS),
    "write_document": ({Role.RUN, Role.OWNER}, EVERY_RUN),
    "submit_review": ({Role.RUN}, ["review"]),
    "dismiss_finding": ({Role.RUN, Role.OWNER}, ["build"]),
    "ask_question": ({Role.RUN}, READERS),
    "list_questions": ({Role.RUN, Role.COORDINATOR, Role.OWNER}, READERS),
    "answer_question": ({Role.OWNER}, []),
    "search_memory": ({Role.RUN, Role.COORDINATOR, Role.OWNER}, READERS),
    "propose_memory": ({Role.RUN, Role.COORDINATOR, Role.OWNER}, EVERY_RUN),
    "list_runs": ({Role.COORDINATOR, Role.OWNER}, []),
    "start_run": ({Role.OWNER}, []),
    "stop_run": ({Role.OWNER}, []),
    "start_worktree": ({Role.OWNER}, []),
    "get_checks": ({Role.RUN, Role.COORDINATOR, Role.OWNER}, READERS),
    "run_checks": ({Role.OWNER}, []),
}


def _actors() -> list[tuple[str, Actor]]:
    return [
        *((f"run:{stage}", _run(stage)) for stage in [*READERS, "judge"]),
        ("coordinator", COORDINATOR),
        ("owner", OWNER),
    ]


def test_the_table_names_the_twenty_two_tools_of_the_design() -> None:
    assert set(policy.TOOLS) == set(EXPECTED)
    assert len(policy.TOOLS) == 23


@pytest.mark.parametrize("tool", sorted(EXPECTED))
def test_each_tool_is_callable_by_exactly_the_roles_and_stages_the_design_lists(
    tool: str,
) -> None:
    roles, stages = EXPECTED[tool]
    for label, actor in _actors():
        wanted = (
            actor.role in roles
            if actor.role is not Role.RUN
            else Role.RUN in roles and actor.stage in stages
        )
        assert policy.may_call(actor, tool) is wanted, f"{tool} for {label}"


def test_a_build_run_lists_thirteen_tools_a_review_run_thirteen_the_owner_twenty() -> None:
    names = list(policy.TOOLS)
    assert len(policy.visible(_run("build"), names)) == 13
    assert len(policy.visible(_run("spec"), names)) == 12
    assert len(policy.visible(_run("split"), names)) == 12
    assert len(policy.visible(_run("review"), names)) == 13
    assert len(policy.visible(COORDINATOR, names)) == 11
    # submit_review and ask_question are run tools: the owner answers questions, never asks them.
    assert len(policy.visible(OWNER, names)) == 20


@pytest.mark.parametrize("role", ROLES)
def test_a_review_role_reads_and_records_notes_and_writes_nothing(role: str) -> None:
    assert policy.visible(_run(role), list(policy.TOOLS)) == [
        "whoami",
        "get_ticket",
        "list_activity",
        "post_note",
        *(["get_qa_holdout"] if role == "qa" else []),
        "read_document",
        "ask_question",
        "list_questions",
        "search_memory",
        "get_checks",
    ]
    assert policy.writable_documents(_run(role)) == []


def test_the_visible_tools_keep_the_order_they_were_given() -> None:
    assert policy.visible(OWNER, ["b", "get_ticket", "whoami"]) == ["get_ticket", "whoami"]


def test_an_unknown_tool_is_called_by_no_one() -> None:
    assert policy.may_call(OWNER, "merge_ticket") is False


def test_a_run_reaches_its_own_ticket_by_default_or_by_name() -> None:
    run = _run("build")
    assert policy.scope_ticket(run, None) == "CF-12"
    assert policy.scope_ticket(run, "CF-12") == "CF-12"


def test_a_run_is_refused_every_other_ticket_with_the_same_sentence_whether_or_not_it_exists() -> (
    None
):
    expected = (
        "out_of_scope: this run is scoped to CF-12; CF-13 is not available to it. "
        "Use ask_question if you need something from another ticket."
    )
    given = _run("build")
    with pytest.raises(ForbiddenError) as other:
        policy.scope_ticket(given, "CF-13")
    assert str(other.value) == expected


def test_owner_and_coordinator_must_name_the_ticket_and_may_name_any() -> None:
    for actor in (OWNER, COORDINATOR):
        assert policy.scope_ticket(actor, "CF-7") == "CF-7"
        with pytest.raises(BadRequestError, match="ticket_id is required"):
            policy.scope_ticket(actor, None)


@pytest.mark.parametrize(
    ("stage", "writable"),
    [
        ("spec", ["mock", "notes", "requirements", "spec", "uat"]),
        ("build", ["notes"]),
        ("review", ["notes"]),
        ("split", ["notes"]),
    ],
)
def test_a_run_writes_only_the_documents_of_its_stage(stage: str, writable: list[str]) -> None:
    run = _run(stage)
    assert policy.writable_documents(run) == writable
    for name in writable:
        policy.check_document_write(run, name)
    with pytest.raises(ForbiddenError, match=f"a {stage} run may not write review"):
        policy.check_document_write(run, "review")  # submit_review writes it, never a run directly


@pytest.mark.parametrize(
    ("stage", "document", "sentence"),
    [
        ("build", "spec", "forbidden: a build run may not write spec. Writable here: notes."),
        (
            "spec",
            "review",
            (
                "forbidden: a spec run may not write review. "
                "Writable here: mock, notes, requirements, spec and uat."
            ),
        ),
    ],
)
def test_the_refusal_names_the_document_and_what_the_run_may_write_instead(
    stage: str, document: str, sentence: str
) -> None:
    given = _run(stage)
    with pytest.raises(ForbiddenError) as refused:
        policy.check_document_write(given, document)
    assert str(refused.value) == sentence


def test_the_owner_writes_any_document() -> None:
    policy.check_document_write(OWNER, "review")
    assert policy.writable_documents(OWNER) is None


@pytest.mark.parametrize(
    ("actor", "kind", "limit"),
    [
        (_run("build"), "follow_up_tickets", 3),
        (_run("split"), "follow_up_tickets", 50),
        (COORDINATOR, "follow_up_tickets", 10),
        (OWNER, "follow_up_tickets", None),
        (_run("build"), "memory_proposals", 5),
        (COORDINATOR, "memory_proposals", 5),
        (OWNER, "memory_proposals", None),
    ],
)
def test_quotas_are_three_follow_ups_fifty_for_a_split_and_five_proposals(
    actor: Actor, kind: str, limit: int | None
) -> None:
    assert policy.quota(actor, kind) == limit


def test_the_nth_use_is_allowed_and_the_next_is_refused_with_what_to_do() -> None:
    run = _run("build")
    policy.check_quota(run, "follow_up_tickets", used=2)
    with pytest.raises(ForbiddenError) as refused:
        policy.check_quota(run, "follow_up_tickets", used=3)
    assert str(refused.value) == (
        "limit: 3 follow-up tickets already created by this run. Put the rest in notes."
    )
    policy.check_quota(OWNER, "follow_up_tickets", used=10_000)


def test_a_run_and_a_coordinator_stay_in_their_own_repository_and_the_owner_goes_anywhere() -> None:
    for actor in (_run("build"), COORDINATOR):
        assert policy.scope_repository(actor, None) == "/r"
        assert policy.scope_repository(actor, "/r") == "/r"
        with pytest.raises(ForbiddenError) as refused:
            policy.scope_repository(actor, "/elsewhere")
        assert str(refused.value) == (
            "out_of_scope: this token is scoped to repository /r; "
            "/elsewhere is not available to it."
        )
    assert policy.scope_repository(OWNER, "/elsewhere") == "/elsewhere"
    assert policy.scope_repository(OWNER, None) is None


def test_every_tool_scopes_a_ticket_with_the_coordinators_repository_check() -> None:
    """`policy.scope_ticket` skips the repository check a coordinator needs; tools use
    `scope.scope_ticket`, so granting a coordinator a tool never opens another repository."""
    tools = [
        path for path in (ROOT / "src" / "code_factory").rglob("*.py")
        if "tools" in path.parts or path.name == "tools.py"
    ]  # fmt: skip
    partial = [str(p) for p in tools if "policy.scope_ticket(" in p.read_text(encoding="utf-8")]
    assert tools
    assert partial == []
