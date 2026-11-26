"""What a call would do, the rule that would allow it and when the board's policy settles it.
The summaries, kinds and suggestions are the previous implementation's golden; the paths and
the refusal counts are worked by hand."""

import json
from pathlib import Path
from typing import Any

import pytest

from code_factory.agents.rules.permissions import (
    ESCALATE_AFTER,
    SANDBOXED,
    SUGGEST_AFTER,
    WAIT_SECONDS,
    answer_history,
    escalation,
    outside_tree,
    refused_in_a_row,
    request_kind,
    routine,
    shown_whole,
    standing_rules,
    suggestions,
    summary,
)

GOLDEN = json.loads(
    (Path(__file__).parent.parent / "golden" / "agents" / "permissions.json").read_text(
        encoding="utf-8"
    )
)
MAIN, TREE = "/r/main", "/r/main/.worktrees/CF-1"


@pytest.mark.parametrize("case", GOLDEN["calls"], ids=[c["summary"][:20] for c in GOLDEN["calls"]])
def test_the_summary_and_the_kind_are_those_of_the_golden(case: dict[str, Any]) -> None:
    assert summary(case["tool"], case["input"]) == case["summary"]
    assert request_kind(case["tool"], case["input"]) == case["kind"]


def test_the_waits_and_thresholds_are_the_boards() -> None:
    assert (WAIT_SECONDS, SUGGEST_AFTER, ESCALATE_AFTER) == (540, 5, 3)
    assert SANDBOXED == "a command inside the run's sandbox"


def test_a_shell_command_is_shown_as_written_and_cut_at_300_characters() -> None:
    assert summary("Bash", {"command": "ls -l"}) == "ls -l"
    assert len(summary("Bash", {"command": "x" * 301})) == 300
    assert shown_whole("Bash", {"command": "x" * 300})
    assert not shown_whole("Bash", {"command": "x" * 301})


def test_another_tool_is_shown_as_its_json_and_counted_in_characters_not_bytes() -> None:
    assert summary("Edit", {"file_path": "a", "old": "é"}) == '{"file_path": "a", "old": "é"}'
    wide = {"k": "é" * 291}
    assert len(json.dumps(wide, ensure_ascii=False)) == 300
    assert shown_whole("Edit", wide)
    assert not shown_whole("Edit", {"k": "é" * 292})
    assert not shown_whole("Bash", {"command": 5, "k": "x" * 300})


@pytest.mark.parametrize(
    ("command", "kind"),
    [
        ("ls", "Bash(ls *)"),
        ("git status", "Bash(git status *)"),
        ("git -C x status", "Bash(git *)"),
        ("  npm\ttest  ", "Bash(npm test *)"),
        ("a | b", None),
        ("a && b", None),
        ("a; b", None),
        ("a > f", None),
        ("a < f", None),
        ("a `b`", None),
        ("a\nb", None),
        ("a\rb", None),
        ("echo $(x)", None),
        ("", None),
    ],
)
def test_a_command_is_a_standing_rule_of_its_first_two_words_unless_it_is_compound(
    command: str, kind: str | None
) -> None:
    assert request_kind("Bash", {"command": command}) == kind


def test_a_tool_other_than_a_shell_is_its_own_kind_and_no_name_is_none() -> None:
    assert request_kind("Edit", {}) == "Edit"
    assert request_kind("", {}) is None
    assert request_kind("Bash", {}) is None


def test_the_standing_rules_are_the_array_of_texts_in_order() -> None:
    assert standing_rules('["Edit", "Bash(ls *)", 3, true, null, [1], {"a": 1}]') == [
        "Edit",
        "Bash(ls *)",
        "3",
        "True",
        "None",
    ]
    for text in (None, "", "not json", '{"a": 1}', '"x"'):
        assert standing_rules(text) == []


def history(answers: list[dict[str, Any]], extra: str = "") -> str:
    return "".join(json.dumps(a) + "\n" for a in answers) + extra


@pytest.mark.parametrize("case", GOLDEN["histories"])
def test_the_suggestions_are_those_of_the_golden(case: dict[str, Any]) -> None:
    text = history(case["answers"], case["extra"])
    assert [list(s) for s in suggestions(text, case["rules"])] == case["suggestions"]


def test_the_history_counts_allowed_over_all_by_kind_in_kind_order() -> None:
    text = (
        '{"kind": "b", "allowed": true}\n{"kind": "a", "allowed": false}\n'
        '{"kind": "b", "allowed": 0}\nnot json\n[1]\n{"allowed": true}\n{"kind": [1]}\n'
    )
    assert answer_history(text) == {"": (0, 1), "None": (1, 1), "a": (0, 1), "b": (1, 2)}
    assert list(answer_history(text)) == ["", "None", "a", "b"]


def test_a_kind_is_suggested_at_five_unanimous_allows_and_not_at_four_or_with_a_refusal() -> None:
    four = history([{"kind": "k", "allowed": True}] * 4)
    five = history([{"kind": "k", "allowed": True}] * 5)
    mixed = history([{"kind": "k", "allowed": True}] * 5 + [{"kind": "k", "allowed": False}])
    assert suggestions(four, []) == []
    assert suggestions(five, []) == [("k", 5)]
    assert suggestions(mixed, []) == []
    assert suggestions(five, ["k"]) == []


def test_a_read_outside_the_tree_is_refused_and_inside_it_is_not() -> None:
    inside = {"file_path": f"{TREE}/src/a.py"}
    assert outside_tree("Read", inside, MAIN, TREE) is None
    assert outside_tree("Read", {"file_path": "src/a.py"}, MAIN, TREE) is None
    assert outside_tree("Read", {"file_path": "/elsewhere/a"}, MAIN, TREE) == (
        f"/elsewhere/a is outside your worktree {TREE}; use paths inside it"
    )


def test_a_path_of_the_main_checkout_is_named_with_its_place_in_the_tree() -> None:
    said = outside_tree("Read", {"file_path": f"{MAIN}/src/a.py"}, MAIN, TREE)
    assert said == (
        f"{MAIN}/src/a.py is outside your worktree; use {TREE}/src/a.py, "
        "the same file in this run's tree"
    )


def test_a_shell_command_naming_a_main_checkout_path_outside_the_tree_is_refused() -> None:
    for command in (
        f"cat {MAIN}/x.py",
        f'cat "{MAIN}/x.py"',
        f"cat '{MAIN}/x.py'",
        f"(cat {MAIN}/x.py)",
        f"a;cat {MAIN}/x.py",
    ):
        said = outside_tree("Bash", {"command": command}, MAIN, TREE)
        assert said is not None, command
        assert said.startswith(f"{MAIN}/x.py is outside your worktree; use {TREE}/x.py")
    for command in (f"cat {TREE}/x.py", "cat /etc/hosts", "ls", f"cat {MAIN}-two/x"):
        assert outside_tree("Bash", {"command": command}, MAIN, TREE) is None, command
    assert outside_tree("Edit", {"file_path": f"{MAIN}/x"}, MAIN, TREE) is None
    assert outside_tree("Bash", {"command": 5}, MAIN, TREE) is None


def board(name: str) -> str:
    return f"mcp__code-factory__{name}"


def test_a_board_read_of_the_runs_own_ticket_is_allowed_and_another_ticket_is_the_owners() -> None:
    own = {"ticket_id": "CF-1"}
    for tool in ("get_ticket", "read_document", "list_activity"):
        assert routine(board(tool), own, MAIN, TREE, "CF-1") == (True, "a read-only board tool")
        assert routine(board(tool), {"ticket_id": "CF-2"}, MAIN, TREE, "CF-1") is None
        assert routine(board(tool), {}, MAIN, TREE, "CF-1") is None


def test_the_memory_search_and_whoami_are_allowed_for_any_input() -> None:
    for tool in ("search_memory", "whoami"):
        assert routine(board(tool), {}, MAIN, TREE, "CF-1") == (True, "a read-only board tool")


def test_a_board_write_or_another_servers_tool_is_the_owners() -> None:
    for tool in ("write_document", "post_note", "create_ticket", "propose_memory"):
        assert routine(board(tool), {"ticket_id": "CF-1"}, MAIN, TREE, "CF-1") is None
    assert routine("mcp__other__search_memory", {}, MAIN, TREE, "CF-1") is None
    assert routine("Bash", {"command": "ls"}, MAIN, TREE, "CF-1") is None


def test_a_request_reaching_outside_the_tree_is_refused_before_the_board_reads() -> None:
    said = routine("Read", {"file_path": f"{MAIN}/a"}, MAIN, TREE, "CF-1")
    assert said == (False, outside_tree("Read", {"file_path": f"{MAIN}/a"}, MAIN, TREE))
    assert said is not None
    assert said[1].endswith("the same file in this run's tree")


def decision(by: str, verdict: str) -> dict[str, str]:
    return {"by": by, "decision": verdict}


def test_refusals_in_a_row_count_the_policys_denials_from_the_latest_back() -> None:
    log = [decision("owner", "allow"), decision("policy", "deny"), decision("policy", "deny")]
    assert refused_in_a_row(log) == 2
    assert refused_in_a_row([*log, decision("policy", "allow")]) == 0
    assert refused_in_a_row([*log, decision("owner", "deny")]) == 0
    assert refused_in_a_row([decision("policy", "deny")] * 3) == 3
    assert refused_in_a_row([]) == 0
    assert refused_in_a_row([{"by": "policy"}, decision("policy", "deny")]) == 1


def test_the_escalation_note_says_how_many_and_why() -> None:
    assert escalation(3, "x is outside") == (
        "the board's policy refused 3 requests in a row: x is outside"
    )
