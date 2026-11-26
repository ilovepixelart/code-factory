"""A tracker's HTTP answers as the adapter reads them: Jira page after page."""

import httpx
from pydantic import SecretStr

from code_factory.delivery.adapters.trackers import read_jira
from code_factory.delivery.models import Tracker

SITE = "https://acme.atlassian.net"


def _issue(key: str) -> dict[str, object]:
    return {"key": key, "fields": {"summary": key}}


async def test_jira_is_read_page_after_page_until_its_last() -> None:
    asked: list[dict[str, str]] = []
    pages = {
        None: {"issues": [_issue("S-1")], "nextPageToken": "p2", "isLast": False},
        "p2": {"issues": [_issue("S-2")], "isLast": True},
    }

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(dict(request.url.params))
        return httpx.Response(200, json=pages[request.url.params.get("nextPageToken")])

    tracker = Tracker(kind="jira", url=SITE, key=SecretStr("k"), jql="project = S", email="a@b")
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        items = await read_jira(client, tracker)

    assert [i.url for i in items] == [f"{SITE}/browse/S-1", f"{SITE}/browse/S-2"]
    assert [(a["jql"], a.get("nextPageToken")) for a in asked] == [
        ("project = S", None),
        ("project = S", "p2"),
    ]
    assert "issuelinks" in asked[0]["fields"]
