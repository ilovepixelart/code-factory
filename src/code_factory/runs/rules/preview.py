"""Where a ticket's live preview is opened."""

from urllib.parse import urlsplit

from code_factory.platform.network import http_url


def preview_address(board: str, port: int) -> str:
    """The link to a preview on `port`, never on the board's own host.

    The owner's cookie is set on the board's host alone, so the other name holds none: `127.0.0.1`
    for a board that names itself `localhost`, `localhost` for any other name. The link goes
    through the board's `/preview/<port>` on that name when the board has a port of its own, else
    straight to the preview.
    """
    parts = urlsplit(board)
    try:
        board_port = parts.port
    except ValueError:
        board_port = None
    name = "127.0.0.1" if parts.hostname in {None, "localhost"} else "localhost"
    if board_port is None:
        return http_url(name, port, "/")
    return http_url(name, board_port, f"/preview/{port}")
