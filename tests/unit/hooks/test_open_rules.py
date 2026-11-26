"""Which pages the board opens a browser on, and the sign-in link that lands there."""

import pytest

from code_factory.hooks.rules.open_board import board_page, opens_board, owner_link


@pytest.mark.parametrize("page", ["/", "/inbox", "/tickets/CF-1?x=1", "/a/b#c", "/t?a=1&b=2"])
def test_a_path_on_the_board_is_a_page(page: str) -> None:
    assert board_page(page) == page


@pytest.mark.parametrize(
    "page",
    [
        "https://example.com",
        "//example.com",
        "/\\example.com",
        "inbox",
        "",
        "/in box",
        "/in\tbox",
        "/in\nbox",
        "/\x00x",
        "/x\x7f",
        "/a" + chr(0xA0) + "b",
        "\\\\evil",
    ],
)
def test_anything_a_browser_could_read_as_another_host_is_not_a_page(page: str) -> None:
    assert board_page(page) is None


def test_the_owner_link_for_the_front_page_has_no_destination() -> None:
    assert owner_link("http://127.0.0.1:8080", "ab12", "/") == "http://127.0.0.1:8080/owner/ab12"


def test_the_owner_link_carries_the_page_form_encoded() -> None:
    base = "http://127.0.0.1:8080"

    assert owner_link(base, "ab12", "/inbox") == f"{base}/owner/ab12?to=%2Finbox"
    assert (
        owner_link(base, "ab12", "/t?a=1&b=2#x") == f"{base}/owner/ab12?to=%2Ft%3Fa%3D1%26b%3D2%23x"
    )
    assert owner_link(base, "ab12", "/a~b*c") == f"{base}/owner/ab12?to=%2Fa%7Eb*c"


@pytest.mark.parametrize(
    ("terminal", "no_open", "opens"),
    [(True, False, True), (True, True, False), (False, False, False), (False, True, False)],
)
def test_only_a_terminal_without_no_open_opens_the_board(
    *, terminal: bool, no_open: bool, opens: bool
) -> None:
    assert opens_board(terminal=terminal, no_open=no_open) is opens
