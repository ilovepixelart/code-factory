"""Tracker answers read as items to file: Linear issues, Jira issues and Slack messages.

The shapes are those of Linear's GraphQL `issues`, Jira Cloud's `GET /rest/api/3/search/jql`
and Slack's `conversations.history`; a value of another shape is left out, never guessed.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from code_factory.delivery.models import TrackerItem

TITLE_LIMIT = 120
# Linear's priority numbers: 0 is none.
_LINEAR_PRIORITY = {1: "urgent", 2: "high", 3: "medium", 4: "low"}
# Jira's two built-in priority schemes: Highest to Lowest, and the older Blocker to Trivial.
_JIRA_PRIORITY = {
    "highest": "urgent",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "lowest": "low",
    "blocker": "urgent",
    "critical": "high",
    "major": "medium",
    "minor": "low",
    "trivial": "low",
}
LINEAR_CLOSED = ("completed", "canceled", "duplicate")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SLACK_LINK = re.compile(r"<([^<>|]+)\|([^<>]+)>")
_SLACK_BARE = re.compile(r"<([^<>|]+)>")


def _dict(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: object) -> Sequence[Any]:
    return value if isinstance(value, list) else []


def _date(value: object) -> str:
    text = str(value or "")
    return text if _DATE.fullmatch(text) else ""


def _kind(names: Sequence[str]) -> str:
    return "bug" if any(name.strip().lower() == "bug" for name in names) else "feature"


def linear_query(label: str, *, assigned: bool) -> str:
    """The `issues` query of open issues, those labelled `label` and, when asked, the key's own."""
    closed = ", ".join(_graphql_string(state) for state in LINEAR_CLOSED)
    conditions = [f"state: {{ type: {{ nin: [{closed}] }} }}"]
    if label:
        conditions.append(f"labels: {{ name: {{ eq: {_graphql_string(label)} }} }}")
    if assigned:
        conditions.append("assignee: { isMe: { eq: true } }")
    return (
        f"{{ issues(first: 100, filter: {{ {', '.join(conditions)} }}) {{ nodes {{ "
        "url title description priority dueDate labels { nodes { name } } parent { url } "
        "inverseRelations { nodes { type issue { url } } } } } }"
    )


def _graphql_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def linear_items(answer: object) -> list[TrackerItem]:
    """The issues of a Linear `issues` query answer."""
    nodes = _list(_dict(_dict(_dict(answer).get("data")).get("issues")).get("nodes"))
    items = []
    for node in map(_dict, nodes):
        url = str(node.get("url") or "")
        if not url:
            continue
        labels = [
            name
            for name in (
                str(_dict(n).get("name") or "")
                for n in _list(_dict(node.get("labels")).get("nodes"))
            )
            if name
        ]
        priority = node.get("priority")
        blockers = [
            str(_dict(relation.get("issue")).get("url") or "")
            for relation in map(_dict, _list(_dict(node.get("inverseRelations")).get("nodes")))
            if relation.get("type") == "blocks"
        ]
        items.append(
            TrackerItem(
                url=url,
                title=str(node.get("title") or url),
                body=str(node.get("description") or ""),
                labels=labels,
                kind=_kind(labels),
                priority=_LINEAR_PRIORITY.get(int(priority), "")
                if isinstance(priority, int | float)
                else "",
                due=_date(node.get("dueDate")),
                parent=str(_dict(node.get("parent")).get("url") or ""),
                blocked_by=[url for url in blockers if url],
            )
        )
    return items


def _marks(text: str, marks: Sequence[Any]) -> str:
    for mark in map(_dict, marks):
        kind = mark.get("type")
        if kind == "code":
            text = f"`{text}`"
        elif kind == "strong":
            text = f"**{text}**"
        elif kind == "em":
            text = f"*{text}*"
        elif kind == "link":
            text = f"[{text}]({_dict(mark.get('attrs')).get('href') or ''})"
    return text


def _inline(nodes: Sequence[Any]) -> str:
    out = []
    for node in map(_dict, nodes):
        kind = node.get("type")
        if kind == "text":
            out.append(_marks(str(node.get("text") or ""), _list(node.get("marks"))))
        elif kind == "hardBreak":
            out.append("\n")
        elif kind == "mention":
            out.append(str(_dict(node.get("attrs")).get("text") or ""))
        elif kind == "inlineCard":
            out.append(str(_dict(node.get("attrs")).get("url") or ""))
        else:
            out.append(_inline(_list(node.get("content"))))
    return "".join(out)


def _block(node: Mapping[str, Any], bullet: str = "") -> str:
    kind, content = node.get("type"), _list(node.get("content"))
    if kind == "heading":
        level = int(_dict(node.get("attrs")).get("level") or 1)
        return f"{'#' * min(max(level, 1), 6)} {_inline(content)}"
    if kind == "codeBlock":
        return f"```\n{_inline(content)}\n```"
    if kind in {"bulletList", "orderedList"}:
        lines = []
        for at, item in enumerate(map(_dict, content), start=1):
            mark = "-" if kind == "bulletList" else f"{at}."
            inner = "\n".join(_block(_dict(child)) for child in _list(item.get("content")))
            lines.append(f"{bullet}{mark} {inner}")
        return "\n".join(lines)
    if kind == "blockquote":
        return "\n".join(f"> {line}" for line in adf_markdown(node).splitlines())
    if kind in {"rule", "paragraph"}:
        return "---" if kind == "rule" else _inline(content)
    return adf_markdown(node)


def adf_markdown(document: object) -> str:
    """Markdown for a Jira field in the Atlassian document format; a string passes as it is."""
    if isinstance(document, str):
        return document
    blocks = [_block(_dict(child)) for child in _list(_dict(document).get("content"))]
    return "\n\n".join(block for block in blocks if block)


def jira_items(answer: object, site: str) -> list[TrackerItem]:
    """The issues of a Jira search answer, each linked under `site`; done ones are left out."""
    items = []
    for issue in map(_dict, _list(_dict(answer).get("issues"))):
        key = str(issue.get("key") or "")
        fields = _dict(issue.get("fields"))
        category = _dict(_dict(fields.get("status")).get("statusCategory")).get("key")
        if not key or category == "done":
            continue
        labels = [str(label) for label in _list(fields.get("labels"))]
        kind = str(_dict(fields.get("issuetype")).get("name") or "")
        priority = str(_dict(fields.get("priority")).get("name") or "").lower()
        browse = f"{site.rstrip('/')}/browse/"
        parent = str(_dict(fields.get("parent")).get("key") or "")
        blockers = [
            browse + str(_dict(link.get("inwardIssue")).get("key"))
            for link in map(_dict, _list(fields.get("issuelinks")))
            if _dict(link.get("type")).get("name") == "Blocks"
            and _dict(link.get("inwardIssue")).get("key")
        ]
        items.append(
            TrackerItem(
                url=f"{site.rstrip('/')}/browse/{key}",
                title=str(fields.get("summary") or key),
                body=adf_markdown(fields.get("description")),
                labels=labels,
                kind=_kind([kind, *labels]),
                priority=_JIRA_PRIORITY.get(priority, ""),
                due=_date(fields.get("duedate")),
                parent=browse + parent if parent else "",
                blocked_by=blockers,
            )
        )
    return items


JIRA_FIELDS = "summary,description,labels,issuetype,priority,duedate,status,parent,issuelinks"


def slack_markdown(text: str) -> str:
    """Slack's message markup as markdown: `<url|label>` and `<url>` links read as links."""
    return _SLACK_BARE.sub(r"\1", _SLACK_LINK.sub(r"[\2](\1)", text))


def slack_messages(answer: object, reaction: str) -> list[tuple[str, str]]:
    """(ts, text) of the history answer's messages that carry `reaction`, oldest first."""
    found = []
    for message in map(_dict, _list(_dict(answer).get("messages"))):
        names = {str(_dict(r).get("name") or "") for r in _list(message.get("reactions"))}
        ts = str(message.get("ts") or "")
        text = str(message.get("text") or "").strip()
        if reaction in names and ts and text:
            found.append((ts, text))
    return list(reversed(found))


def slack_item(permalink: str, text: str) -> TrackerItem:
    """A Slack message as an item: its first line the title, the whole message the body."""
    body = slack_markdown(text)
    first = body.splitlines()[0]
    title = first if len(first) <= TITLE_LIMIT else first[: TITLE_LIMIT - 1] + "…"
    return TrackerItem(
        url=permalink, title=title, body=body, labels=[], kind="feature", priority="", due=""
    )
