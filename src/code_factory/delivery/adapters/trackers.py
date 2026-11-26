"""The trackers' HTTP APIs: one read of each, its answer handed back as JSON."""

import httpx

from code_factory.delivery.models import Tracker, TrackerItem
from code_factory.delivery.rules.trackers import (
    JIRA_FIELDS,
    jira_items,
    linear_items,
    linear_query,
    slack_item,
    slack_messages,
)
from code_factory.platform.errors import CodeFactoryError

TIMEOUT_S = 20.0
# At most this many pages of 100 issues per poll.
JIRA_PAGES = 10


class TrackerError(CodeFactoryError):
    """A tracker refused or did not answer; the message names which and why."""


def _answer(kind: str, response: httpx.Response) -> object:
    if response.status_code != httpx.codes.OK:
        msg = f"{kind} answered {response.status_code}: check the key and its address in [intake]"
        raise TrackerError(msg)
    answer = response.json()
    if kind == "slack" and not (isinstance(answer, dict) and answer.get("ok")):
        error = answer.get("error") if isinstance(answer, dict) else "no answer"
        raise TrackerError(f"slack refused: {error}")
    return answer


async def read_linear(client: httpx.AsyncClient, tracker: Tracker) -> list[TrackerItem]:
    """Open Linear issues the key sees, with the label and, when set, assigned to the key."""
    response = await client.post(
        tracker.url,
        json={"query": linear_query(tracker.label, assigned=tracker.assigned)},
        headers={"Authorization": tracker.key.get_secret_value()},
    )
    return linear_items(_answer("linear", response))


async def read_jira(client: httpx.AsyncClient, tracker: Tracker) -> list[TrackerItem]:
    """Issues of the repository's JQL that are not done, page after page up to `JIRA_PAGES`.

    The search answers a `nextPageToken` until its last page; without following it, issues past
    the first page would never come in, since every poll would read the same first page.
    """
    items: list[TrackerItem] = []
    token: str | None = None
    for _ in range(JIRA_PAGES):
        params: dict[str, str | int] = {
            "jql": tracker.jql,
            "fields": JIRA_FIELDS,
            "maxResults": 100,
        }
        if token is not None:
            params["nextPageToken"] = token
        response = await client.get(
            f"{tracker.url.rstrip('/')}/rest/api/3/search/jql",
            params=params,
            auth=(tracker.email, tracker.key.get_secret_value()),
        )
        answer = _answer("jira", response)
        items += jira_items(answer, tracker.url)
        found = answer.get("nextPageToken") if isinstance(answer, dict) else None
        if not isinstance(found, str) or not found:
            break
        token = found
    return items


async def read_slack(client: httpx.AsyncClient, tracker: Tracker) -> list[TrackerItem]:
    """Messages of the channel carrying the reaction, each linked by its permalink."""
    api = tracker.url.rstrip("/")
    headers = {"Authorization": f"Bearer {tracker.key.get_secret_value()}"}
    history = await client.get(
        f"{api}/conversations.history",
        params={"channel": tracker.channel, "limit": 100},
        headers=headers,
    )
    items = []
    for ts, text in slack_messages(_answer("slack", history), tracker.reaction):
        link = await client.get(
            f"{api}/chat.getPermalink",
            params={"channel": tracker.channel, "message_ts": ts},
            headers=headers,
        )
        permalink = _answer("slack", link)
        url = permalink.get("permalink") if isinstance(permalink, dict) else None
        if isinstance(url, str) and url:
            items.append(slack_item(url, text))
    return items


_READERS = {"linear": read_linear, "jira": read_jira, "slack": read_slack}


async def read_tracker(tracker: Tracker) -> list[TrackerItem]:
    """The items `tracker` holds for the board; `TrackerError` when it cannot be read."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            return await _READERS[tracker.kind](client, tracker)
    except httpx.HTTPError as error:
        raise TrackerError(f"{tracker.kind} could not be reached: {error}") from error
