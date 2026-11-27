"""The listen address `serve` takes and the link the board names itself by."""

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from urllib.parse import urlunsplit

from code_factory.platform.errors import BadRequestError

NETWORK_WARNING = (
    "serving on a network address: requests and the sign-in cookie travel unencrypted on that "
    "network unless you have verified that this interface belongs to an encrypted overlay "
    "network; the cookie is the owner's long-lived credential, and anyone who reads it on the "
    "network can act as the owner"
)

_V4_RANGES = tuple(
    IPv4Network(block)
    for block in (
        "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
    )
)  # fmt: skip
_V6_RANGES = (IPv6Network("::1/128"), IPv6Network("fc00::/7"))


def _in_range(address: IPv4Address | IPv6Address) -> bool:
    """Whether the address is in a range of its own family (a family never matches the other's)."""
    if isinstance(address, IPv4Address):
        return any(address in block for block in _V4_RANGES)
    return any(address in block for block in _V6_RANGES)


def listen_address(text: str) -> IPv4Address | IPv6Address:
    """One literal loopback or private address, else a refusal.

    Private means `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10` (an overlay
    network) and `fc00::/7`, each matched within its own family. `ipaddress` alone would take an
    IPv4-mapped IPv6 address (`::ffff:127.0.0.1`) as loopback, which no range here does, and a
    scope id (`::1%lo`) is refused outright.

    Raises:
        BadRequestError: The text is not one such address.
    """
    refusal = BadRequestError(
        f"--address takes one literal private or loopback address: {text} is not one"
    )
    if "%" in text:
        raise refusal
    try:
        address = ip_address(text)
    except ValueError:
        raise refusal from None
    if not _in_range(address):
        raise refusal
    return address


def network_warning(address: IPv4Address | IPv6Address) -> str | None:
    """The sentence to print for a non-loopback address, None for a loopback one."""
    return None if address.is_loopback else NETWORK_WARNING


def board_url(address: IPv4Address | IPv6Address, port: int, both: bool) -> str:
    """The link of the board.

    `localhost` is named only for `127.0.0.1` when the board holds `::1` on the port too, since
    `localhost` may resolve to either; any other address is named itself, an IPv6 one in brackets.
    """
    if both and address == IPv4Address("127.0.0.1"):
        return http_url("localhost", port)
    return http_url(str(address), port)


def http_url(host: str, port: int, path: str = "", query: str = "") -> str:
    """A link to the board or a preview on `host:port`, an IPv6 host in brackets.

    Plain HTTP: the board serves no TLS, on loopback or, with `NETWORK_WARNING`, a private network.
    """
    netloc = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return urlunsplit(("http", netloc, path, query, ""))
