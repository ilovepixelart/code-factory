"""Which pages a capture shows, which it refuses, and the images it names."""

import pytest

from code_factory.screens.rules import IMAGE, image_stem, images_of, page_refusal, pages_of


def test_a_ticket_without_pages_shows_its_own_page() -> None:
    assert pages_of(" ", "sample", "CF-3") == ["/tickets/sample/CF-3"]
    assert pages_of("/agents, /inbox#perm-1", "sample", "CF-3") == ["/agents", "/inbox#perm-1"]


@pytest.mark.parametrize(
    ("page", "refusal"),
    [
        ("/agents", None),
        ("/inbox#perm-1", None),
        ("agents", "agents is not a path on the board: a page starts with /"),
        ("@evil.example/x", "@evil.example/x is not a path on the board: a page starts with /"),
        (
            "/inbox#a b",
            (
                "/inbox#a b names no section the capture can scroll to: after # comes an element "
                "id of letters, digits, - and _"
            ),
        ),
    ],
)
def test_a_page_is_a_path_on_the_board_and_its_section_an_id(
    page: str, refusal: str | None
) -> None:
    assert page_refusal(page) == refusal


def test_images_are_plain_names_in_light_then_dark() -> None:
    images = images_of(["/tickets/sample/CF-3", "/"])
    assert images == [
        "tickets-sample-CF-3-light.png", "tickets-sample-CF-3-dark.png",
        "board-light.png", "board-dark.png",
    ]  # fmt: skip
    assert all(IMAGE.fullmatch(name) for name in images)
    assert image_stem("/inbox#perm-1") == "inbox-perm-1"
