"""A production error report filed as a bug ticket, counted when it repeats."""

from datetime import UTC, datetime, timedelta

import pytest

from code_factory.hooks.models import ErrorReported, ReleaseFact
from code_factory.hooks.ports import TicketFacts
from code_factory.platform.errors import BadRequestError, NotFoundError
from hooks_fakes import Fakes

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
REPORT = {
    "fingerprint": "checkout-500",
    "title": "Checkout answers 500",
    "message": "TypeError at cart.ts:12",
}


async def test_the_first_report_of_a_fingerprint_files_one_bug() -> None:
    fakes = Fakes()

    reported = await fakes.service().report_error("sample", REPORT, NOW)

    assert reported == ErrorReported(ticket_id="CF-101", count=1, created=True)
    (bug,) = fakes.tickets.bugs
    assert (bug.repository, bug.title, bug.source, bug.caused_by) == (
        "sample",
        "Checkout answers 500",
        "error:checkout-500",
        [],
    )
    assert bug.description == (
        "Reported by code-factory error with the fingerprint checkout-500.\n\n"
        "TypeError at cart.ts:12"
    )


async def test_a_report_with_no_title_is_titled_by_its_fingerprint() -> None:
    fakes = Fakes()

    await fakes.service().report_error("sample", {"fingerprint": "f-1"}, NOW)

    assert fakes.tickets.bugs[0].title == "Production error f-1"
    assert fakes.tickets.bugs[0].description == (
        "Reported by code-factory error with the fingerprint f-1."
    )


async def test_a_repeat_is_counted_on_the_ticket_with_its_message() -> None:
    fakes = Fakes()
    fakes.tickets.sources[("sample", "error:checkout-500")] = TicketFacts(
        id="CF-9", repository="sample", title="x", stage="spec"
    )

    second = await fakes.service().report_error("sample", REPORT, NOW)
    fakes.tickets.report_counts["CF-9"] = 1
    third = await fakes.service().report_error("sample", REPORT, NOW)

    assert (second, third) == (
        ErrorReported(ticket_id="CF-9", count=2, created=False),
        ErrorReported(ticket_id="CF-9", count=3, created=False),
    )
    assert fakes.tickets.recorded[0] == (
        "CF-9",
        "reported",
        {"message": "TypeError at cart.ts:12"},
        "error report",
    )
    assert fakes.tickets.bugs == []


async def test_a_report_with_no_one_line_fingerprint_is_a_bad_request() -> None:
    fakes = Fakes()

    service = fakes.service()
    with pytest.raises(BadRequestError, match=r"^a report needs a one-line fingerprint$"):
        await service.report_error("sample", {"fingerprint": "a\nb"}, NOW)

    assert fakes.tickets.bugs == []


async def test_an_untracked_repository_is_not_found() -> None:
    service = Fakes().service()
    with pytest.raises(NotFoundError, match="nowhere"):
        await service.report_error("nowhere", REPORT, NOW)


async def test_a_secret_in_the_message_never_reaches_the_ticket() -> None:
    fakes = Fakes()

    await fakes.service().report_error(
        "sample", {"fingerprint": "f", "message": "boom with sk-abcdef123456"}, NOW
    )

    assert "sk-abcdef123456" not in fakes.tickets.bugs[0].description
    assert "[redacted]" in fakes.tickets.bugs[0].description


def shipped(days_ago: float, version: str = "1.0.0") -> ReleaseFact:
    return ReleaseFact(
        version=version, at=(NOW - timedelta(days=days_ago)).timestamp(), tickets=["CF-1", "CF-2"]
    )


async def test_a_report_inside_the_window_of_the_newest_release_names_its_tickets() -> None:
    fakes = Fakes()
    fakes.releases.releases = [shipped(3)]

    await fakes.service().report_error("sample", REPORT, NOW)

    bug = fakes.tickets.bugs[0]
    assert bug.caused_by == ["CF-1", "CF-2"]
    assert bug.description.endswith(
        "TypeError at cart.ts:12\n\n"
        "Seen within the verification window of release 1.0.0, which shipped CF-1, CF-2."
    )


async def test_a_report_naming_its_release_names_that_release_even_after_the_window() -> None:
    fakes = Fakes()
    fakes.releases.releases = [shipped(30, "0.9.0"), shipped(20, "1.0.0")]

    await fakes.service().report_error("sample", {**REPORT, "release": "0.9.0"}, NOW)

    assert fakes.tickets.bugs[0].description.endswith(
        "Reported against release 0.9.0, which shipped CF-1, CF-2."
    )


async def test_the_watch_follows_the_repositorys_watch_days_and_defaults_to_seven() -> None:
    fakes = Fakes()
    fakes.releases.releases = [shipped(10)]
    await fakes.service().report_error("sample", {"fingerprint": "a"}, NOW)
    fakes.releases.days = 14
    await fakes.service().report_error("sample", {"fingerprint": "b"}, NOW)
    fakes.releases.days = 0
    await fakes.service().report_error("sample", {"fingerprint": "c"}, NOW)

    assert [bug.caused_by for bug in fakes.tickets.bugs] == [[], ["CF-1", "CF-2"], []]


async def test_a_report_that_loses_the_race_to_file_the_ticket_is_counted_on_the_winner() -> None:
    fakes = Fakes()
    fakes.tickets.raced_by = TicketFacts(id="CF-9", repository="sample", title="x", stage="spec")

    reported = await fakes.service().report_error("sample", REPORT, NOW)

    assert reported == ErrorReported(ticket_id="CF-9", count=2, created=False)
    assert fakes.tickets.recorded[0][:2] == ("CF-9", "reported")
