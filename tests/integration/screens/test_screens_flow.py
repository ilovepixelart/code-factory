"""A capture waits on the Inbox, its images are served, and the owner approves or sends it back."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from code_factory.platform.errors import BadRequestError
from code_factory.screens.service import NONE_WAITS, ScreensService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import ActivityService, TicketService

TREE = "a1b2c3d4e5f6"
PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture
async def shot(app: FastAPI, tmp_path: Path) -> str:
    """A ticket whose capture of `TREE` waits, its image on disk."""
    services = app.state.services
    screens = ScreensService(
        services.get(TicketService), services.get(ActivityService), tmp_path / "captures"
    )
    services.add(ScreensService, screens)
    ticket = await services.get(TicketService).create(
        NewTicket(repository="sample", title="New checkout page"), by="owner"
    )
    folder = screens.folder_of("sample", ticket.id, TREE)
    folder.mkdir(parents=True)
    (folder / "light.png").write_bytes(PNG)
    (folder / "unlisted.png").write_bytes(PNG)
    await screens.record(ticket.id, TREE, ["light.png"], by="run:1")
    return str(ticket.id)


async def test_a_waiting_capture_is_on_the_inbox_and_its_image_is_served(
    client: httpx.AsyncClient, shot: str
) -> None:
    [item] = (await client.get("/api/inbox")).json()["screens"]
    image = await client.get(f"/api/captures/sample/{shot}/{TREE}/light.png")

    assert (item["ticket"]["id"], item["reason"], item["images"]) == (shot, TREE, ["light.png"])
    assert (image.status_code, image.content) == (200, PNG)


async def test_approving_answers_the_capture_once(client: httpx.AsyncClient, shot: str) -> None:
    path = f"/api/tickets/sample/{shot}/screens-approval"

    approved = await client.post(path)
    again = await client.post(path)

    assert approved.json() == {"notice": f"Approved the screens of {shot}", "undo": None}
    assert (again.status_code, again.json()["detail"]) == (409, NONE_WAITS)
    assert (await client.get("/api/inbox")).json()["screens"] == []


async def test_sending_back_needs_a_reason_and_records_it(
    app: FastAPI, client: httpx.AsyncClient, shot: str
) -> None:
    path = f"/api/tickets/sample/{shot}/screens-changes"

    blank = await client.post(path, json={"reason": " "})
    sent = await client.post(path, json={"reason": "The button is cut off"})

    assert (blank.status_code, blank.json()["detail"]) == (400, "say what should change")
    assert sent.json()["notice"] == f"Sent the screens of {shot} back"
    page = await app.state.services.get(ActivityService).list_activity(
        shot, kinds=["capture_changes"]
    )
    assert [i.data for i in page.items] == [{"tree": TREE, "reason": "The button is cut off"}]


@pytest.mark.parametrize(
    "tail",
    [
        f"{TREE}/unlisted.png",
        f"{TREE}/dark.png",
        f"{TREE}/light.txt",
        "nothex/light.png",
        f"{TREE}/..%2Flight.png",
    ],
)
async def test_an_image_no_capture_lists_is_404(
    client: httpx.AsyncClient, shot: str, tail: str
) -> None:
    answer = await client.get(f"/api/captures/sample/{shot}/{tail}")
    assert answer.status_code == 404


async def test_a_before_capture_is_recorded_and_never_waits_on_the_owner(app: FastAPI) -> None:
    services = app.state.services
    screens = services.get(ScreensService)
    ticket = await services.get(TicketService).create(
        NewTicket(repository="sample", title="Retitle the cart"), by="owner"
    )

    await screens.record_before(ticket.id, TREE, ["light.png"], by="owner:shoot")
    page = await services.get(ActivityService).list_activity(ticket.id, kinds=["capture_before"])

    assert [(i.kind, i.data) for i in page.items] == [
        ("capture_before", {"tree": TREE, "images": ["light.png"]})
    ]
    assert ticket.id not in {c.ticket for c in await screens.waiting()}


async def test_a_before_capture_with_a_path_for_a_name_is_refused(app: FastAPI) -> None:
    screens = app.state.services.get(ScreensService)

    with pytest.raises(BadRequestError, match="by plain name"):
        await screens.record_before("CF-1", TREE, ["../x.png"], by="owner:shoot")
