"""Branch names, ticket tree names and digests, against git's own check and SHA-256 vectors."""

import re
import subprocess

import pytest

from code_factory.git.rules.branches import (
    attempt_branch,
    attempt_tree_name,
    branch_for,
    branch_refusal,
    is_plain_segment,
    wip_ref,
)
from code_factory.git.rules.digests import short_digest, tree_name

REFUSED = {
    "feat/é": (
        "it holds a non-ASCII character, which a case-folding file system can read as another ref"
    ),
    "FETCH_HEAD": "it looks like a top-level ref such as FETCH_HEAD, which git reads as that ref",
    "ORIG_HEAD": "it looks like a top-level ref such as FETCH_HEAD, which git reads as that ref",
    "origin/main": "it starts with origin/, which git reads as another ref",
    "Origin/main": "it starts with origin/, which git reads as another ref",
    "refs/heads/x": "it starts with refs/, which git reads as another ref",
    "heads/x": "it starts with heads/, which git reads as another ref",
    "-x": "it starts with -, which git reads as an option",
    "HEAD": "HEAD is git's name for the checked-out commit",
    "@": "@ is git's name for the checked-out commit",
    "a" * 40: "it is a full commit id, which git reads as that commit",
    "a" * 64: "it is a full commit id, which git reads as that commit",
    "a b": "it holds a space, which git refuses in a branch name",
    "a~b": "it holds ~, which git refuses in a branch name",
    "a\x01b": "it holds a control character, which git refuses in a branch name",
    "a..b": "it holds .., which git reads as a range",
    "a@{b": "it holds @{, which git reads as a reflog or upstream expression",
    "/a": "it starts with /",
    "a/": "it ends with /",
    "a//b": "it holds //",
    "a.": "it ends with .",
    "a/.b": "a part of it starts with .",
    "a.lock/b": "a part of it ends with .lock",
}
ACCEPTED = ["ticket/cf-12", "feat/x", "a.b", "main", "feature/ABC_1", "a" * 39, "HEADx", "head"]


@pytest.mark.parametrize(("name", "why"), REFUSED.items())
def test_a_name_is_refused_with_the_rule_it_breaks(name: str, why: str) -> None:
    assert branch_refusal(name) == why


@pytest.mark.parametrize("name", ACCEPTED)
def test_a_plain_branch_name_is_accepted(name: str) -> None:
    assert branch_refusal(name) is None


# Names git rejects must all be refused; what git accepts and the board refuses is only these.
def _board_only(name: str) -> bool:
    return (
        name == "@"
        or re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", name) is not None
        or name.startswith("-")
        or name.lower().startswith(("origin/", "remotes/", "refs/", "heads/", "tags/"))
        or re.fullmatch(r"[A-Z0-9_]*HEAD", name) is not None
        or not name.isascii()
    )


def _git_accepts(name: str) -> bool:
    done = subprocess.run(  # noqa: S603  # a fixed argv, the names are data
        ["git", "check-ref-format", "--branch", name],  # noqa: S607
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


def test_every_name_git_rejects_is_refused_and_the_extras_are_only_the_board_ones() -> None:
    names = [*REFUSED, *ACCEPTED, "a:b", "a?b", "a*b", "a[b", "a\\b", "a^b", "a/b.lock", ".x", "x/"]
    for name in names:
        if name.startswith("-"):
            continue  # git reads it as an option; the board refuses it by its own rule
        accepted = _git_accepts(name)
        refused = branch_refusal(name) is not None
        assert refused or accepted, name
        if refused and accepted:
            assert _board_only(name), name


def test_a_ticket_id_is_one_plain_segment() -> None:
    assert [
        is_plain_segment(text) for text in ("CF-12", "a_b", "x", "", "-a", "a/b", "..", "a b")
    ] == [
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
    ]


def test_names_derived_from_a_ticket_id() -> None:
    assert wip_ref("CF-12") == "refs/wip/CF-12"
    assert branch_for("CF-12") == "ticket/cf-12"
    assert attempt_tree_name("CF-12", 0) == "CF-12"
    assert attempt_tree_name("CF-12", 2) == "CF-12-2"
    assert attempt_branch("ticket/cf-12", 0) == "ticket/cf-12"
    assert attempt_branch("ticket/cf-12", 2) == "ticket/cf-12-attempt-2"


def test_the_digests_match_sha256_vectors() -> None:
    assert short_digest("abc") == "ba7816bf8f01cfea"  # FIPS 180-2 test vector
    assert tree_name("a", "b", "c") == "8badde10c760e9b7"  # printf 'a\0b\0c' | shasum -a 256
