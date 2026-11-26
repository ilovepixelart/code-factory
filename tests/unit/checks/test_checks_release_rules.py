"""When a release is verified, the bug a failure files, and the remote claim boundaries."""

from datetime import UTC, datetime, timedelta

import pytest

from code_factory.checks.models import ReleaseRef
from code_factory.checks.rules import (
    claim_holds,
    decline_live,
    log_tail,
    offer_live,
    refusal_sentence,
    verify_bug,
    verify_due,
)

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def release(age: timedelta, tickets: list[str] | None = None) -> ReleaseRef:
    return ReleaseRef(version="1.2.0", at=NOW - age, tickets=tickets or [])


def test_a_verification_is_due_inside_the_window_and_not_after_it() -> None:
    assert verify_due("make verify", release(7 * DAY), NOW, None, 7)
    assert not verify_due("make verify", release(7 * DAY + timedelta(seconds=1)), NOW, None, 7)


def test_the_window_defaults_to_seven_days_and_zero_turns_it_off() -> None:
    assert verify_due("make verify", release(3 * DAY), NOW, None, None)
    assert not verify_due("make verify", release(8 * DAY), NOW, None, None)
    assert not verify_due("make verify", release(DAY), NOW, None, 0)


def test_a_verification_is_hourly_strict_at_3600_seconds() -> None:
    newest = release(DAY)
    assert not verify_due("c", newest, NOW, NOW - timedelta(seconds=3599), 7)
    assert verify_due("c", newest, NOW, NOW - timedelta(seconds=3600), 7)


def test_no_command_or_no_release_means_nothing_is_due() -> None:
    assert not verify_due(None, release(DAY), NOW, None, 7)
    assert not verify_due("", release(DAY), NOW, None, 7)
    assert not verify_due("c", None, NOW, None, 7)


def test_the_bug_names_the_release_and_quotes_the_masked_tail() -> None:
    bug = verify_bug(release(DAY, ["CF-1", "CF-2"]), "make verify", 3, "/s/v.log", "boom")
    assert bug.title == "Release 1.2.0 fails its verification"
    assert (bug.type, bug.labels, bug.priority) == ("bug", ["release"], "high")
    assert bug.caused_by == ["CF-1", "CF-2"]
    assert bug.description == (
        "Filed by the board: `make verify` ended with exit code 3 while release 1.2.0 was inside "
        "its verification window. Log: /s/v.log\n\n```\nboom\n```"
    )


def test_a_release_naming_no_tickets_causes_nothing() -> None:
    assert verify_bug(release(DAY), "c", 1, "/l", "t").caused_by == []


def test_the_tail_is_the_last_forty_lines() -> None:
    text = "\n".join(f"line {n}" for n in range(1, 51))
    tail = log_tail(text)
    assert tail.splitlines()[0] == "line 11"
    assert tail.splitlines()[-1] == "line 50"
    assert len(tail.splitlines()) == 40
    assert log_tail("a\nb") == "a\nb"


@pytest.mark.parametrize(("age", "holds"), [(59, True), (60, False), (0, True), (61, False)])
def test_a_claim_holds_below_sixty_seconds(age: int, holds: bool) -> None:
    assert claim_holds(NOW - timedelta(seconds=age), NOW) is holds


@pytest.mark.parametrize(("age", "live"), [(599, True), (600, False)])
def test_an_offer_is_live_below_600_seconds(age: int, live: bool) -> None:
    assert offer_live(NOW - timedelta(seconds=age), NOW) is live


@pytest.mark.parametrize(("age", "live"), [(86399, True), (86400, False)])
def test_a_decline_is_live_below_a_day(age: int, live: bool) -> None:
    assert decline_live(NOW - timedelta(seconds=age), NOW) is live


def test_the_four_refusals_are_worded_as_the_runner_reads_them() -> None:
    assert refusal_sentence("not_yours", "CF-1") == (
        "the claim on CF-1's checks is not yours: claim again"
    )
    assert refusal_sentence("head_moved", "CF-1") == (
        "the pull request's head moved since the claim: CF-1's result is refused"
    )
    assert refusal_sentence("other_head", "CF-1") == (
        "the result is for another head than CF-1's claimed head"
    )
    assert refusal_sentence("tree_differs", "CF-1") == (
        "the tree checked is not the claimed head's tree: CF-1's result is refused"
    )
