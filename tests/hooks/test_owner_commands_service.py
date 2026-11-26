"""`open`, `sign-out` and `audit export` through the service, with fakes for the neighbours."""

import re
from datetime import UTC, datetime

import pytest

from code_factory.hooks.models import OpenerUnavailableError
from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.tickets.models import Activity
from hooks_fakes import Fakes

BASE = "http://127.0.0.1:8080"


async def test_open_signs_the_browser_in_with_a_fresh_nonce_and_never_prints_it() -> None:
    fakes = Fakes()

    opened = await fakes.service().open_board("/inbox")

    assert fakes.opener.opened == [f"{BASE}/owner/nonce1?to=%2Finbox"]
    assert opened.line == f"opened {BASE}/inbox in the default browser"
    assert "nonce1" not in opened.line
    assert fakes.auth.minted == ["nonce1"]
    assert fakes.auth.spent == []
    assert fakes.probe.asked == [BASE]


async def test_open_with_no_page_lands_on_the_front_page_with_no_destination() -> None:
    fakes = Fakes()

    opened = await fakes.service().open_board()

    assert fakes.opener.opened == [f"{BASE}/owner/nonce1"]
    assert opened.line == f"opened {BASE}/ in the default browser"


async def test_open_uses_the_port_it_is_given_over_the_configured_one() -> None:
    fakes = Fakes()

    opened = await fakes.service().open_board("/", port=9090)

    assert opened.line == "opened http://127.0.0.1:9090/ in the default browser"
    assert fakes.probe.asked == ["http://127.0.0.1:9090"]


@pytest.mark.parametrize(
    "page", ["https://example.com", "//example.com", "/\\example.com", "inbox"]
)
async def test_open_refuses_a_page_off_the_board_before_it_asks_anything(page: str) -> None:
    fakes = Fakes()

    with pytest.raises(
        BadRequestError, match=r"^the page must be a path on the board, such as /inbox$"
    ):
        await fakes.service().open_board(page)

    assert (fakes.probe.asked, fakes.auth.minted, fakes.opener.opened) == ([], [], [])


async def test_open_with_no_board_answering_says_to_start_it_and_mints_nothing() -> None:
    fakes = Fakes()
    fakes.probe.answers = False

    with pytest.raises(
        UnavailableError,
        match=f"^no board answers at {BASE}: start code-factory serve first$",
    ):
        await fakes.service().open_board("/")

    assert (fakes.auth.minted, fakes.opener.opened) == ([], [])


@pytest.mark.parametrize(
    ("error", "why"),
    [
        (
            OpenerUnavailableError("no program opens a browser here"),
            "no program opens a browser here",
        ),
        (OSError("exited with 2"), "exited with 2"),
    ],
)
async def test_open_with_no_browser_spends_the_nonce_and_says_how_to_sign_in(
    error: Exception, why: str
) -> None:
    fakes = Fakes()
    fakes.opener.error = error

    with pytest.raises(
        UnavailableError,
        match=f"^could not open a browser: {why}; run code-factory sign-in for the link$",
    ):
        await fakes.service().open_board("/inbox")

    assert (fakes.auth.minted, fakes.auth.spent) == (["nonce1"], ["nonce1"])


async def test_sign_out_gives_how_many_sessions_it_ended() -> None:
    fakes = Fakes()
    fakes.auth.ended = 3

    assert await fakes.service().sign_out() == 3


def record(
    at: str, *, ticket: str = "CF-1", by: str = "alex", kind: str = "k", **data: object
) -> Activity:
    return Activity(
        id=1,
        ticket_id=ticket,
        at=datetime.fromisoformat(at).astimezone(UTC),
        kind=kind,
        by=by,
        data=dict(data),
    )


async def test_the_export_is_every_record_since_the_day_in_the_order_at_repository_ticket() -> None:
    fakes = Fakes()
    fakes.tickets.records = [
        ("web", record("2026-11-02T08:00:00+00:00", kind="board_write")),
        ("api", record("2026-11-02T11:00:00+00:00", kind="hold_released", commit="abc")),
        ("web", record("2026-11-02T08:00:00+00:00", ticket="CF-0", kind="a")),
        ("api", record("2026-11-02T08:00:00+00:00", ticket="CF-5", kind="b")),
        ("api", record("2026-10-31T23:59:59+00:00")),
        ("api", record("2026-11-01T00:00:00+00:00", kind="first")),
        ("api", record("2026-11-05T00:00:00+00:00", by="")),
    ]

    lines = await fakes.service().audit_export("2026-11-01")

    assert [(x["at"], x["repository"], x["ticket"], x["kind"]) for x in lines] == [
        ("2026-11-01T00:00:00Z", "api", "CF-1", "first"),
        ("2026-11-02T08:00:00Z", "api", "CF-5", "b"),
        ("2026-11-02T08:00:00Z", "web", "CF-0", "a"),
        ("2026-11-02T08:00:00Z", "web", "CF-1", "board_write"),
        ("2026-11-02T11:00:00Z", "api", "CF-1", "hold_released"),
    ]
    assert lines[4]["detail"] == {"commit": "abc"}


@pytest.mark.parametrize(
    "since", ["", "yesterday", "2026-13-01", "2026-02-30", "2026-1-1", "2026-11-01T00:00"]
)
async def test_the_export_refuses_what_is_not_a_day(since: str) -> None:
    with pytest.raises(BadRequestError, match=f'^"{re.escape(since)}" is not a day as YYYY-MM-DD$'):
        await Fakes().service().audit_export(since)
