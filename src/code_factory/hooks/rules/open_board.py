"""Which pages the board opens a browser on, and the sign-in link that lands there."""

from urllib.parse import quote_plus


def board_page(page: str) -> str | None:
    r"""The page when it is one path on the board, else `None`.

    One leading `/` and not `//`, no `\\`, whitespace or control character: a browser reads `\\`
    as `/` and drops tabs and newlines, which would turn the page into another host.
    """
    if not page.startswith("/") or page.startswith("//"):
        return None
    if any(char == "\\" or char.isspace() or not char.isprintable() for char in page):
        return None
    return page


def owner_link(base: str, nonce: str, page: str) -> str:
    """The sign-in link of the board at `base`: the nonce in the path, the page in `to`."""
    link = f"{base}/owner/{nonce}"
    if page == "/":
        return link
    # The form encoding keeps `*` and encodes `~`, as a browser's URLSearchParams does.
    return f"{link}?to={quote_plus(page, safe='*').replace('~', '%7E')}"


def opens_board(*, terminal: bool, no_open: bool) -> bool:
    """Whether a command that starts the board opens it in a browser."""
    return terminal and not no_open
