"""Tracker answers read as tickets, in the shapes the trackers' API references document."""

import pytest

from code_factory.delivery.models import TrackerItem
from code_factory.delivery.rules import behaviour_section, pull_body, screens_line
from code_factory.delivery.rules.trackers import (
    adf_markdown,
    jira_items,
    linear_items,
    linear_query,
    slack_item,
    slack_markdown,
    slack_messages,
)


def test_a_linear_issue_keeps_its_priority_due_date_labels_and_bug_type() -> None:
    answer = {
        "data": {
            "issues": {
                "nodes": [
                    {
                        "url": "https://linear.app/acme/issue/ENG-1/x",
                        "title": "Crash on save",
                        "description": "Steps:\n\n1. Save",
                        "priority": 2,
                        "dueDate": "2026-12-01",
                        "labels": {"nodes": [{"name": "Bug"}, {"name": "ios"}]},
                    },
                    {"url": "https://linear.app/acme/issue/ENG-2/y", "title": "Y", "priority": 0},
                    {"title": "no url"},
                ]
            }
        }
    }

    assert linear_items(answer) == [
        TrackerItem(
            url="https://linear.app/acme/issue/ENG-1/x",
            title="Crash on save",
            body="Steps:\n\n1. Save",
            labels=["Bug", "ios"],
            kind="bug",
            priority="high",
            due="2026-12-01",
        ),
        TrackerItem(
            url="https://linear.app/acme/issue/ENG-2/y",
            title="Y",
            body="",
            labels=[],
            kind="feature",
            priority="",
            due="",
        ),
    ]


def test_the_linear_query_asks_for_open_labelled_issues_and_quotes_the_label() -> None:
    query = linear_query('say "hi"', assigned=True)

    assert 'state: { type: { nin: ["completed", "canceled", "duplicate"] } }' in query
    assert 'labels: { name: { eq: "say \\"hi\\"" } }' in query
    assert "assignee: { isMe: { eq: true } }" in query
    assert "assignee" not in linear_query("", assigned=False)


def test_a_jira_issue_becomes_a_ticket_and_a_done_one_is_left_out() -> None:
    description = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Totals are off."}]},
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "run "},
                                    {"type": "text", "text": "make", "marks": [{"type": "code"}]},
                                ],
                            }
                        ],
                    }
                ],
            },
        ],
    }
    answer = {
        "issues": [
            {
                "key": "SHOP-7",
                "fields": {
                    "summary": "Export totals",
                    "description": description,
                    "labels": ["reports"],
                    "issuetype": {"name": "Bug"},
                    "priority": {"name": "Highest"},
                    "duedate": "2026-12-24",
                    "status": {"statusCategory": {"key": "indeterminate"}},
                },
            },
            {
                "key": "SHOP-8",
                "fields": {"summary": "Old", "status": {"statusCategory": {"key": "done"}}},
            },
        ],
        "isLast": True,
    }

    assert jira_items(answer, "https://acme.atlassian.net/") == [
        TrackerItem(
            url="https://acme.atlassian.net/browse/SHOP-7",
            title="Export totals",
            body="Totals are off.\n\n- run `make`",
            labels=["reports"],
            kind="bug",
            priority="urgent",
            due="2026-12-24",
        )
    ]


def test_a_jira_story_is_a_feature_and_lowest_is_low() -> None:
    answer = {
        "issues": [
            {
                "key": "S-1",
                "fields": {
                    "summary": "S",
                    "issuetype": {"name": "Story"},
                    "priority": {"name": "Lowest"},
                },
            }
        ]
    }

    assert [(i.kind, i.priority, i.body) for i in jira_items(answer, "https://x")] == [
        ("feature", "low", "")
    ]


def test_adf_headings_code_and_links_read_as_markdown() -> None:
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Why"}],
            },
            {"type": "codeBlock", "content": [{"type": "text", "text": "x = 1"}]},
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "docs",
                        "marks": [{"type": "link", "attrs": {"href": "https://d"}}],
                    }
                ],
            },
        ],
    }

    assert adf_markdown(doc) == "## Why\n\n```\nx = 1\n```\n\n[docs](https://d)"
    assert adf_markdown(None) == ""


def test_slack_messages_with_the_reaction_are_taken_oldest_first() -> None:
    answer = {
        "ok": True,
        "messages": [
            {"ts": "3.0", "text": "newest", "reactions": [{"name": "ticket", "count": 1}]},
            {"ts": "2.0", "text": "no reaction"},
            {"ts": "1.0", "text": "oldest", "reactions": [{"name": "ticket", "count": 2}]},
        ],
    }

    assert slack_messages(answer, "ticket") == [("1.0", "oldest"), ("3.0", "newest")]


def test_a_slack_message_reads_as_markdown_with_its_first_line_the_title() -> None:
    item = slack_item(
        "https://acme.slack.com/archives/C1/p1", "Login fails\n<https://a|see log> <https://b>"
    )

    assert (item.title, item.body, item.url) == (
        "Login fails",
        "Login fails\n[see log](https://a) https://b",
        "https://acme.slack.com/archives/C1/p1",
    )
    assert slack_markdown("x" * 3) == "xxx"


def test_the_behaviour_section_opens_the_pull_request_description() -> None:
    notes = (
        "# Notes\n\n- [x] step\n\n## Behaviour\n\n| Before | After |\n|---|---|\n| a | b |\n\n"
        "## Later\n\nx\n"
    )
    section = behaviour_section(notes)

    assert section == "## Behaviour\n\n| Before | After |\n|---|---|\n| a | b |"
    assert pull_body("T", [], "main", "abc", section).endswith(section + "\n")
    assert behaviour_section("# Notes\n\n## Behaviour\n\n") == ""


KINDS = ("capture", "capture_approved", "capture_changes", "capture_before")


def test_the_latest_capture_and_its_verdict_reach_the_pull_request() -> None:
    old = {"tree": "a" * 40, "images": ["x.png"]}
    new = {"tree": "b" * 40, "images": ["y.png", "z.png"]}
    approved_old = {"tree": "a" * 40}

    waiting = screens_line(
        [("capture", old), ("capture_approved", approved_old), ("capture", new)], KINDS
    )
    approved = screens_line([("capture", new), ("capture_approved", {"tree": "b" * 40})], KINDS)

    assert waiting == (
        "Screens: the latest capture, of tree bbbbbbbbbbbb (2 images), is waiting for the owner; "
        "The images are on the ticket's page on the board."
    )
    assert "is approved by the owner" in approved
    assert screens_line([], KINDS) == ""


def test_a_linear_issue_names_its_parent_and_the_issues_that_block_it() -> None:
    node = {
        "url": "https://linear.app/a/issue/E-3/x",
        "title": "X",
        "parent": {"url": "https://linear.app/a/issue/E-1/p"},
        "inverseRelations": {
            "nodes": [
                {"type": "blocks", "issue": {"url": "https://linear.app/a/issue/E-2/b"}},
                {"type": "related", "issue": {"url": "https://linear.app/a/issue/E-4/r"}},
            ]
        },
    }

    [item] = linear_items({"data": {"issues": {"nodes": [node]}}})

    assert (item.parent, item.blocked_by) == (
        "https://linear.app/a/issue/E-1/p",
        ["https://linear.app/a/issue/E-2/b"],
    )
    assert "inverseRelations { nodes { type issue { url } } }" in linear_query("", assigned=False)


def test_a_jira_issue_names_its_parent_and_its_inward_blockers_only() -> None:
    blocks = {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"}
    fields = {
        "summary": "X",
        "parent": {"key": "S-1"},
        "issuelinks": [
            {"type": blocks, "inwardIssue": {"key": "S-2"}},
            {"type": blocks, "outwardIssue": {"key": "S-3"}},
            {"type": {"name": "Relates"}, "inwardIssue": {"key": "S-4"}},
        ],
    }

    [item] = jira_items({"issues": [{"key": "S-5", "fields": fields}]}, "https://j")

    assert (item.parent, item.blocked_by) == ("https://j/browse/S-1", ["https://j/browse/S-2"])


def test_the_before_capture_of_the_default_branch_is_set_beside_the_change() -> None:
    before = {"tree": "c" * 40, "images": ["p.png", "q.png"]}
    after = {"tree": "d" * 40, "images": ["p.png", "q.png"]}

    both = screens_line([("capture_before", before), ("capture", after)], KINDS)
    alone = screens_line([("capture_before", before)], KINDS)

    assert both == (
        "Screens: the latest capture, of tree dddddddddddd (2 images), is waiting for the owner; "
        "Before: the default branch's tree cccccccccccc (2 images). The images are on the "
        "ticket's page on the board."
    )
    assert alone == "Screens: Before: the default branch's tree cccccccccccc (2 images)."


@pytest.mark.parametrize(
    ("name", "priority"),
    [("Blocker", "urgent"), ("Critical", "high"), ("Major", "medium"), ("Minor", "low"),
     ("Trivial", "low"), ("Highest", "urgent"), ("Lowest", "low"), ("Custom", "")],
)  # fmt: skip
def test_both_of_jiras_priority_schemes_map_onto_the_boards(name: str, priority: str) -> None:
    answer = {"issues": [{"key": "S-1", "fields": {"summary": "S", "priority": {"name": name}}}]}

    assert [i.priority for i in jira_items(answer, "https://j")] == [priority]
