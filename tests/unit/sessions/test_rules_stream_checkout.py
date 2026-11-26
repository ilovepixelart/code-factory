import json
from pathlib import PurePosixPath

import pytest

from code_factory.sessions.models import Event
from code_factory.sessions.rules import checkout, stream
from code_factory.sessions.rules.redaction import redaction_text
from sessions_values import golden, sample_events


def test_a_frame_is_the_id_and_the_event_in_the_default_layout() -> None:
    event = Event(
        2,
        "s-block",
        None,
        "SessionStart",
        1790000800.0,
        "s-block.jsonl",
        0,
        {"session_id": "s-block", "hook_event_name": "SessionStart", "_captured_at": 1790000800.0},
    )
    assert stream.sse_frame(event) == (
        'id: 2\ndata: {"seq": 2, "session_id": "s-block", "agent_id": null, '
        '"event": "SessionStart", "captured_at": 1790000800.0, "payload": {"session_id": '
        '"s-block", "hook_event_name": "SessionStart", "_captured_at": 1790000800.0}}\n\n'
    )
    assert stream.KEEPALIVE == ": keepalive\n\n"


def test_every_golden_chunk_is_the_frame_of_its_sample_event() -> None:
    by_seq = {event.seq: event for event in sample_events()}
    for case in golden("streams.golden.json"):
        for chunk in case["chunks"]:
            seq = int(chunk.split("\n", 1)[0].removeprefix("id: "))
            assert stream.sse_frame(by_seq[seq]) == chunk


@pytest.mark.parametrize(
    ("after", "header", "expected"),
    [
        (None, None, 0),
        ("", None, 0),
        ("3", None, 3),
        (None, "5", 5),
        ("3", "5", 3),
        ("", "5", 5),
        (" 7 ", None, 7),
        ("-2", None, -2),
        ("x", None, None),
        ("1.5", None, None),
        ("1_0", None, None),
        ("٣", None, None),
        ("9223372036854775808", None, None),
        ("9223372036854775807", None, 9223372036854775807),
        (None, "x", None),
        ("3", "x", 3),
    ],
)
def test_the_position_is_after_else_the_header_else_zero(
    after: str | None, header: str | None, expected: int | None
) -> None:
    assert stream.position(after, header) == expected


def p(text: str) -> PurePosixPath:
    return PurePosixPath(text)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/r/sample/.code-factory/worktrees/CF-2", "/r/sample"),
        ("/r/sample/.code-factory/worktrees/CF-2/src/deep", "/r/sample"),
        ("/r/sample/src", "/r/sample/src"),
        ("/r/sample/worktrees/CF-2", "/r/sample/worktrees/CF-2"),
        ("/r/sample/.code-factory/worktrees", "/r/sample/.code-factory/worktrees"),
        (
            "/r/a/.code-factory/worktrees/x/.code-factory/worktrees/y",
            "/r/a/.code-factory/worktrees/x",
        ),
        ("/", "/"),
    ],
)
def test_a_board_run_tree_stands_for_the_checkout_it_was_made_from(
    path: str, expected: str
) -> None:
    assert checkout.tree_checkout(p(path)) == p(expected)


def test_a_gitdir_pointer_names_an_absolute_or_a_relative_directory() -> None:
    root = p("/r/wt")
    assert checkout.gitdir_of("gitdir: /r/sample/.git/worktrees/wt\n", root) == p(
        "/r/sample/.git/worktrees/wt"
    )
    assert checkout.gitdir_of("gitdir: ../sample/.git/worktrees/wt", root) == p(
        "/r/wt/../sample/.git/worktrees/wt"
    )
    assert checkout.gitdir_of("not a pointer", root) is None


@pytest.mark.parametrize(
    ("gitdir", "main"),
    [
        ("/r/sample/.git/worktrees/wt", "/r/sample"),
        ("/r/sample/.git/modules/sub", None),
        ("/r/sample/worktrees/wt", None),
        ("/r/other/worktrees/wt", None),
    ],
)
def test_a_linked_worktrees_git_directory_leads_to_its_main_checkout(
    gitdir: str, main: str | None
) -> None:
    expected = None if main is None else p(main)
    assert checkout.main_of_worktree_gitdir(p(gitdir)) == expected


@pytest.mark.parametrize(
    ("head", "branch"),
    [
        ("ref: refs/heads/main\n", "main"),
        ("ref: refs/heads/feat/CF-2", "feat/CF-2"),
        ("dcf92c3f1234567890abcdef\n", "dcf92c3f"),
        ("abc", "abc"),
        ("", ""),
    ],
)
def test_a_head_names_a_branch_or_the_first_eight_characters_of_a_revision(
    head: str, branch: str
) -> None:
    assert checkout.branch_of_head(head) == branch


def test_the_redaction_file_lists_references_and_replacements_longest_first() -> None:
    text = redaction_text(
        [("short", "[a]"), ("a much longer find", "[b]"), ("short", "[dup]"), ("", "[none]")],
        ["agent@3", "agent@2"],
    )
    assert json.loads(text) == {
        "references": ["agent@3", "agent@2"],
        "patterns": [["a much longer find", "[b]"], ["short", "[a]"]],
    }


def test_a_find_with_non_ascii_text_also_stands_in_its_escaped_form() -> None:
    parsed = json.loads(redaction_text([('café "x"', "[c]")], []))
    assert parsed["patterns"] == [['caf\\u00e9 \\"x\\"', "[c]"], ['café "x"', "[c]"]]


def test_a_pointer_file_without_the_prefix_still_names_a_directory_for_the_repository() -> None:
    root = p("/r/wt")
    assert checkout.pointer_target("gitdir: /r/s/.git/worktrees/wt\n", root) == p(
        "/r/s/.git/worktrees/wt"
    )
    assert checkout.pointer_target("/r/s/.git/worktrees/wt", root) == p("/r/s/.git/worktrees/wt")
    assert checkout.pointer_target("rel/dir", root) == p("/r/wt/rel/dir")
