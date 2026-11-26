"""The delivery service over a real database, with a scripted gh and fake neighbours."""

from datetime import timedelta

import pytest
from pydantic import SecretStr

from code_factory.checks.models import PullHead
from code_factory.delivery.models import MergeRefusedError, NotReadyError, Tracker, TrackerItem
from code_factory.delivery.module import ChecksForge
from code_factory.delivery.ports import Candidate, DeliveryPorts, Switches
from code_factory.delivery.service import DeliveryForge, DeliveryService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.stages.models import Hold
from code_factory.tickets.models import Ticket
from delivery_fakes import (
    AWS_KEY,
    START,
    TIP,
    URL,
    Clock,
    Fakes,
    Places,
    ScriptedGh,
    pull_answer,
)


@pytest.fixture
def gh() -> ScriptedGh:
    return ScriptedGh()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def fakes(ticket: Ticket) -> Fakes:
    candidate = Candidate(
        id=ticket.id, repository="sample", title="Add x", branch="ticket/cf-1", column="build"
    )
    return Fakes(ticket=candidate)


@pytest.fixture
def ports(fakes: Fakes) -> DeliveryPorts:
    return DeliveryPorts(tickets=fakes, git=fakes, checks=fakes, places=Places(fakes), policy=fakes)


@pytest.fixture
def delivery(
    uow: UnitOfWork, ports: DeliveryPorts, gh: ScriptedGh, clock: Clock
) -> DeliveryService:
    return DeliveryService(uow, ports, gh, clock=clock)


def _ready_to_ship(gh: ScriptedGh) -> None:
    gh.answer(("pr", "list"), [])
    gh.answer(("pr", "create"), URL + "\n")
    gh.answer(("pr", "view"), pull_answer())


async def test_a_finished_branch_is_pushed_by_id_and_its_pull_request_opened(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    _ready_to_ship(gh)

    outcome = await delivery.ship(fakes.ticket.id)

    assert (outcome.shipped, outcome.url) == (True, URL)
    assert fakes.pushed == [(TIP, "ticket/cf-1")]
    create = next(call for call in gh.calls if call[:2] == ["pr", "create"])
    assert create[create.index("--title") + 1] == f"{fakes.ticket.id}: Add x"
    assert create[create.index("--base") + 1] == "main"
    pull = await delivery.pull(fakes.ticket.id)
    assert pull is not None
    assert (pull.url, pull.shipped_head, pull.ci) == (URL, TIP, "passed")
    kinds = [e.kind for e in (await delivery.events([fakes.ticket.id]))[fakes.ticket.id]]
    assert kinds == ["ship_started", "ship_pushed", "pull_request"]


async def test_a_shipped_head_has_its_checks_queued(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    _ready_to_ship(gh)

    await delivery.ship(fakes.ticket.id)

    assert fakes.queued == [(fakes.ticket.id, TIP)]


async def test_commits_pushed_onto_a_shipped_pull_request_have_their_checks_queued(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    _ready_to_ship(gh)
    await delivery.ship(fakes.ticket.id)
    pull = await delivery.pull(fakes.ticket.id)
    assert pull is not None
    fakes.local_tip = "b" * 40

    assert await delivery.ship_added(pull, fakes.ticket)

    assert fakes.queued[-1] == (fakes.ticket.id, "b" * 40)


async def test_a_shipped_ticket_is_not_shipped_again(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    _ready_to_ship(gh)
    await delivery.ship(fakes.ticket.id)

    again = await delivery.ship(fakes.ticket.id)

    assert not again.shipped
    assert sum(1 for call in gh.calls if call[:2] == ["pr", "create"]) == 1


async def test_an_open_pull_request_at_the_same_head_is_recorded_not_created(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    gh.answer(
        ("pr", "list"),
        [{"url": URL, "headRefOid": TIP, "baseRefName": "main", "isCrossRepository": False}],
    )
    gh.answer(("pr", "view"), pull_answer())

    outcome = await delivery.ship(fakes.ticket.id)

    assert (outcome.shipped, outcome.url) == (True, URL)
    assert fakes.pushed == []
    assert not any(call[:2] == ["pr", "create"] for call in gh.calls)


async def test_a_secret_in_a_commit_message_holds_the_ship(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    fakes.commit_messages.append(f"add the key {AWS_KEY}")
    _ready_to_ship(gh)

    outcome = await delivery.ship(fakes.ticket.id)

    assert not outcome.shipped
    assert outcome.reason.startswith("the screen held the push: a secret in commit message 1")
    assert AWS_KEY not in outcome.reason
    assert fakes.pushed == []
    events = (await delivery.events([fakes.ticket.id]))[fakes.ticket.id]
    assert [(e.kind, e.retry_at) for e in events] == [("ship_failed", None)]


async def test_a_transient_create_failure_retries_after_its_wait(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh, clock: Clock
) -> None:
    _ready_to_ship(gh)
    gh.answer(("pr", "create"), "HTTP 502: Bad Gateway", ok=False)

    first = await delivery.ship(fakes.ticket.id)
    clock.now = START + timedelta(seconds=4)
    waiting = await delivery.ship(fakes.ticket.id)
    gh.answer(("pr", "create"), URL + "\n")
    clock.now = START + timedelta(seconds=5)
    later = await delivery.ship(fakes.ticket.id)

    assert not first.shipped
    assert waiting.reason == "a failed ship of this head waits"
    assert later.shipped


async def test_the_owners_retry_ships_a_head_a_failure_holds(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    _ready_to_ship(gh)
    gh.answer(("pr", "create"), "GraphQL: Resource not accessible by integration", ok=False)
    failed = await delivery.ship(fakes.ticket.id)
    held = await delivery.ship(fakes.ticket.id)
    gh.answer(("pr", "create"), URL + "\n")

    retried = await delivery.ship(fakes.ticket.id, retry=True)

    events = (await delivery.events([fakes.ticket.id]))[fakes.ticket.id]
    assert (failed.shipped, held.reason, retried.shipped) == (
        False,
        "a failed ship of this head waits",
        True,
    )
    assert "ship_failed" in [e.kind for e in events]


async def _shipped(delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh) -> None:
    _ready_to_ship(gh)
    await delivery.ship(fakes.ticket.id)


async def test_a_green_shipped_pull_request_merges_at_its_shipped_head(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    await _shipped(delivery, fakes, gh)
    gh.answer(("pr", "merge"), "")

    merged = await delivery.merge(fakes.ticket.id, by="owner")

    assert (merged.url, merged.head) == (URL, TIP)
    assert ["pr", "merge", URL, "--merge", "--match-head-commit", TIP] in gh.calls
    pull = await delivery.pull(fakes.ticket.id)
    assert pull is not None
    assert pull.state == "merged"


async def test_failed_checks_refuse_the_merge_without_calling_github(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    await _shipped(delivery, fakes, gh)
    fakes.checks_verdict = "failed"

    with pytest.raises(NotReadyError, match=f"the board's checks failed on {TIP}"):
        await delivery.merge(fakes.ticket.id)
    assert not any(call[:2] == ["pr", "merge"] for call in gh.calls)


async def test_a_live_head_past_the_shipped_one_is_not_merged(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    await _shipped(delivery, fakes, gh)
    gh.answer(("pr", "view"), pull_answer(head="b" * 40))

    with pytest.raises(NotReadyError, match="head moved"):
        await delivery.merge(fakes.ticket.id)
    assert not any(call[:2] == ["pr", "merge"] for call in gh.calls)


async def test_a_refused_merge_is_recorded_and_waits_before_the_next_try(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh, clock: Clock
) -> None:
    await _shipped(delivery, fakes, gh)
    gh.answer(("pr", "merge"), "HTTP 503", ok=False)

    with pytest.raises(MergeRefusedError, match="GitHub refused the merge: HTTP 503"):
        await delivery.merge(fakes.ticket.id)
    clock.now = START + timedelta(seconds=2)
    with pytest.raises(NotReadyError, match="waits before it is tried again"):
        await delivery.merge(fakes.ticket.id)

    events = (await delivery.events([fakes.ticket.id]))[fakes.ticket.id]
    failed = [e for e in events if e.kind == "merge_failed"]
    assert [(e.head, e.retry_at) for e in failed] == [(TIP, START + timedelta(seconds=5))]


async def test_the_pass_ships_and_merges_a_repository_that_does_not_wait(
    delivery: DeliveryService, gh: ScriptedGh
) -> None:
    _ready_to_ship(gh)
    gh.answer(("pr", "merge"), "")

    report = await delivery.run_pass()

    assert report.steps["ship_finished"] == "1 shipped"
    assert report.steps["merge_finished"] == "1 merged"


@pytest.mark.parametrize("reason", ["waits for review", "large change"])
async def test_a_policy_hold_keeps_automatic_delivery_from_merging(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh, reason: str
) -> None:
    await _shipped(delivery, fakes, gh)
    fakes.hold = Hold(reason=reason, owner=True)

    assert await delivery.merge_finished() == []
    assert fakes.policy_checks == [(fakes.ticket.id, TIP)]
    assert delivery.owner_hold(fakes.ticket.id, TIP) == reason
    assert delivery.owner_hold(fakes.ticket.id, "different") == ""
    assert not any(call[:2] == ["pr", "merge"] for call in gh.calls)
    gh.answer(("pr", "merge"), "")

    assert (await delivery.merge(fakes.ticket.id, by="owner")).head == TIP
    assert delivery.owner_hold(fakes.ticket.id, TIP) == ""


async def test_a_repository_that_waits_for_the_owner_is_not_merged_by_the_pass(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh
) -> None:
    fakes.switches = Switches(ship=True, merge_waits=True)
    _ready_to_ship(gh)

    report = await delivery.run_pass()

    assert report.steps["merge_finished"] == "0 merged"
    assert not any(call[:2] == ["pr", "merge"] for call in gh.calls)


async def test_a_writers_issue_comes_in_once(
    delivery: DeliveryService, fakes: Fakes, gh: ScriptedGh, clock: Clock
) -> None:
    fakes.switches = Switches(github_issues=True)
    issue = {
        "url": "https://github.com/o/r/issues/4", "title": "Crash on save", "body": "It crashes.",
        "labels": [{"name": "bug"}, {"name": "P1"}], "author": {"login": "dev"},
    }  # fmt: skip
    stranger = issue | {"url": "https://github.com/o/r/issues/5", "author": {"login": "x"}}
    gh.answer(("issue", "list"), [issue, stranger])
    gh.answer(("api", "repos/{owner}/{repo}/collaborators/dev/permission"), {"permission": "write"})
    gh.answer(("api", "repos/{owner}/{repo}/collaborators/x/permission"), {"permission": "read"})

    first = await delivery.poll_intake("sample")
    clock.now = START + timedelta(seconds=61)
    second = await delivery.poll_intake("sample")

    assert first == ["CF-901"]
    assert second == []
    made = fakes.created[0]
    assert (made.type, made.priority, made.source) == ("bug", "high", issue["url"])
    assert made.description.startswith("From https://github.com/o/r/issues/4")


async def test_a_trackers_items_come_in_once_linked_to_the_parent_and_blocker_already_in(
    delivery: DeliveryService, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = "https://acme.atlassian.net/browse/"
    epic = TrackerItem(
        url=base + "S-1", title="Gift cards", body="", labels=[], kind="feature", priority="",
        due="",
    )  # fmt: skip
    child = epic.model_copy(
        update={"url": base + "S-2", "title": "Issue codes", "parent": base + "S-1",
                "blocked_by": [base + "S-1", base + "S-9"]}
    )  # fmt: skip
    fakes.switches = Switches(
        trackers=(Tracker(kind="jira", url="https://acme.atlassian.net", key=SecretStr("k")),)
    )

    async def read(tracker: Tracker) -> list[TrackerItem]:  # noqa: ARG001  # one tracker here
        return [epic, child]

    monkeypatch.setattr("code_factory.delivery.service.intake.read_tracker", read)

    first = await delivery.poll_intake("sample")

    assert first == ["CF-901", "CF-902"]
    made = fakes.created[1]
    assert (made.parent, made.blocked_by, made.source) == ("CF-901", ["CF-901"], base + "S-2")


async def test_the_forge_screen_holds_a_secret_push(
    uow: UnitOfWork, ports: DeliveryPorts, fakes: Fakes, gh: ScriptedGh
) -> None:
    fakes.commit_messages.append(f"key {AWS_KEY}")
    forge = DeliveryForge(uow, ports, gh)

    held = await forge.held("sample", "ticket/cf-1", "main", TIP)

    assert held is not None
    assert "secret" in held
    fakes.commit_messages.clear()
    assert await forge.held("sample", "ticket/cf-1", "main", TIP) is None


async def test_the_forge_posts_a_commit_status_through_the_statuses_api(
    uow: UnitOfWork, ports: DeliveryPorts, gh: ScriptedGh
) -> None:
    gh.answer(("api",), "{}")
    forge = DeliveryForge(uow, ports, gh)

    posted = await forge.post_status("sample", TIP, "success", "code-factory/checks", "passed")

    assert posted is True
    assert gh.calls == [
        [
            "api", "--method", "POST", f"repos/{{owner}}/{{repo}}/statuses/{TIP}",
            "-f", "state=success", "-f", "context=code-factory/checks", "-f", "description=passed",
        ]
    ]  # fmt: skip


async def test_a_status_github_refuses_is_not_posted(
    uow: UnitOfWork, ports: DeliveryPorts, gh: ScriptedGh
) -> None:
    gh.answer(("api",), "HTTP 422", ok=False)
    forge = DeliveryForge(uow, ports, gh)

    assert await forge.post_status("sample", TIP, "success", "c", "d") is False


async def test_a_status_for_something_other_than_a_commit_id_never_reaches_gh(
    uow: UnitOfWork, ports: DeliveryPorts, gh: ScriptedGh
) -> None:
    forge = DeliveryForge(uow, ports, gh)

    for commit in ("main", "../pulls", TIP[:39], TIP.upper()):
        assert await forge.post_status("sample", commit, "success", "c", "d") is False
    assert gh.calls == []


async def test_the_checks_forge_reads_the_open_pull_requests_delivery_recorded(
    uow: UnitOfWork, ports: DeliveryPorts, gh: ScriptedGh, delivery: DeliveryService, fakes: Fakes
) -> None:
    _ready_to_ship(gh)
    await delivery.ship(fakes.ticket.id)
    services = Services()
    services.add(DeliveryService, delivery)
    services.add(DeliveryForge, DeliveryForge(uow, ports, gh))
    forge = ChecksForge(services)

    assert await forge.open_pull_heads("sample") == [
        PullHead(repository="sample", ticket_id=fakes.ticket.id, head=TIP)
    ]
    assert await forge.open_pull_heads("other") == []
