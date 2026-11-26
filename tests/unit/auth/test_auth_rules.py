from datetime import UTC, datetime, timedelta

import pytest

from code_factory.auth.models import TokenKind
from code_factory.auth.rules import digest, expiry, kind_of, mint
from code_factory.platform.errors import BadRequestError

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def test_a_token_is_its_prefix_and_the_unpadded_urlsafe_base64_of_32_bytes() -> None:
    # 32 zero bytes encode to 43 'A' characters; 0xfb bytes exercise the url-safe alphabet.
    assert mint(TokenKind.RUN, bytes(32)) == "cfr_" + "A" * 43
    assert mint(TokenKind.OWNER, b"\xfb" * 32) == "cfo_" + "-_v7" * 10 + "-_s"


def test_every_kind_has_its_own_prefix() -> None:
    prefixes = {kind: mint(kind, bytes(32))[:4] for kind in TokenKind}
    assert prefixes == {
        TokenKind.RUN: "cfr_",
        TokenKind.OWNER: "cfo_",
        TokenKind.NONCE: "cfn_",
        TokenKind.SESSION: "cfs_",
    }


@pytest.mark.parametrize("size", [0, 31, 33])
def test_entropy_of_another_size_is_refused(size: int) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        mint(TokenKind.RUN, bytes(size))


def test_the_kind_is_read_from_a_well_formed_token() -> None:
    for kind in TokenKind:
        assert kind_of(mint(kind, b"\x01" * 32)) is kind


@pytest.mark.parametrize(
    "token",
    [
        "",
        "cfr_",
        "cfr_" + "A" * 42,
        "cfr_" + "A" * 44,
        "cfx_" + "A" * 43,
        "xfr_" + "A" * 43,
        "cfr_" + "A" * 42 + "=",
        "cfr_" + "A" * 42 + " ",
    ],
)
def test_a_token_that_is_not_well_formed_has_no_kind(token: str) -> None:
    assert kind_of(token) is None


def test_the_digest_is_the_sha256_hex_of_the_token() -> None:
    # FIPS 180-2 test vector for "abc".
    assert digest("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_expiry_is_now_plus_the_lifetime() -> None:
    assert expiry(NOW, timedelta(hours=2), TokenKind.RUN) == NOW + timedelta(hours=2)


@pytest.mark.parametrize("ttl", [timedelta(0), timedelta(seconds=-1)])
def test_a_lifetime_that_is_not_positive_is_refused(ttl: timedelta) -> None:
    with pytest.raises(BadRequestError, match="lifetime must be longer than zero"):
        expiry(NOW, ttl, TokenKind.RUN)


@pytest.mark.parametrize(
    ("kind", "longest"),
    [
        (TokenKind.RUN, timedelta(days=7)),
        (TokenKind.OWNER, timedelta(days=366)),
        (TokenKind.NONCE, timedelta(minutes=5)),
        (TokenKind.SESSION, timedelta(days=366)),
    ],
)
def test_the_longest_lifetime_is_allowed_and_one_second_more_is_not(
    kind: TokenKind, longest: timedelta
) -> None:
    assert expiry(NOW, longest, kind) == NOW + longest
    given = longest + timedelta(seconds=1)
    with pytest.raises(BadRequestError, match=f"{kind.value} token lifetime is at most"):
        expiry(NOW, given, kind)
