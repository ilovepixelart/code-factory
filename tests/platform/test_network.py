from ipaddress import ip_address

import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.platform.network import (
    NETWORK_WARNING,
    board_url,
    listen_address,
    network_warning,
)

ACCEPTED = [
    "127.0.0.1", "::1", "10.0.0.0", "10.255.255.255", "172.16.0.0", "172.31.255.255",
    "192.168.0.0", "192.168.255.255", "100.64.0.0", "100.127.255.255", "fc00::", "fdff:ffff::1",
    "127.0.0.2",
]  # fmt: skip
REFUSED = [
    "0.0.0.0", "::",  # noqa: S104  # refused addresses, not a bind "example.org", "localhost", "8.8.8.8", "9.255.255.255", "11.0.0.0",
    "172.15.255.255", "172.32.0.0", "192.167.255.255", "192.169.0.0", "100.63.255.255",
    "100.128.0.0", "fbff::1", "fe00::1", "2001:db8::1", "",
    "::1%lo", "::ffff:127.0.0.1", " 127.0.0.1", "0127.0.0.1", "127.0.0.1 ", "::ffff:10.0.0.1",
    "fe80::1", "169.254.1.1", "127.0.0.1/8", "::2",
]  # fmt: skip

WARNING = (
    "serving on a network address: requests and the sign-in cookie travel unencrypted on that "
    "network unless you have verified that this interface belongs to an encrypted overlay "
    "network; the cookie is the owner's long-lived credential, and anyone who reads it on the "
    "network can act as the owner"
)


@pytest.mark.parametrize("text", ACCEPTED)
def test_loopback_and_private_addresses_are_taken(text: str) -> None:
    assert listen_address(text) == ip_address(text)


@pytest.mark.parametrize("text", REFUSED)
def test_anything_else_is_refused_with_the_sentence(text: str) -> None:
    with pytest.raises(BadRequestError) as refused:
        listen_address(text)
    assert str(refused.value) == (
        f"--address takes one literal private or loopback address: {text} is not one"
    )


@pytest.mark.parametrize(
    "text", ["192.168.1.20", "10.0.0.1", "172.16.0.1", "100.64.0.7", "fd00::5"]
)
def test_a_network_address_gets_the_unencrypted_traffic_warning(text: str) -> None:
    assert network_warning(ip_address(text)) == WARNING == NETWORK_WARNING


@pytest.mark.parametrize("text", ["127.0.0.1", "::1"])
def test_a_loopback_address_gets_no_warning(text: str) -> None:
    assert network_warning(ip_address(text)) is None


@pytest.mark.parametrize(
    ("address", "port", "both", "link"),
    [
        ("127.0.0.1", 4000, True, "http://localhost:4000"),
        ("127.0.0.1", 8080, True, "http://localhost:8080"),
        ("127.0.0.1", 4000, False, "http://127.0.0.1:4000"),
        ("192.168.1.20", 4000, True, "http://192.168.1.20:4000"),
        ("10.0.0.5", 4000, False, "http://10.0.0.5:4000"),
        ("127.0.0.2", 4000, True, "http://127.0.0.2:4000"),
        ("::1", 4000, True, "http://[::1]:4000"),
        ("::1", 4000, False, "http://[::1]:4000"),
        ("fd00::5", 4000, True, "http://[fd00::5]:4000"),
    ],
)
def test_the_board_link_says_localhost_only_when_the_board_holds_both_loopbacks(
    address: str, port: int, both: bool, link: str
) -> None:
    assert board_url(ip_address(address), port, both) == link
