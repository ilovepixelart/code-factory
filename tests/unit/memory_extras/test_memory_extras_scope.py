"""Where an entry loads: the terms of its scope (the previous implementation's scope tests)."""

import pytest

from code_factory.memory_extras.rules import (
    check_fields,
    everywhere,
    for_labels,
    for_role,
    is_archived,
    is_core,
    is_glob,
    loads,
    scope_refusal,
    touches,
)
from memory_extras_values import entry

REFUSED = ["bulid", "core, stage", "build,", "label:"]
ALLOWED = [
    "",
    "core",
    "archive",
    "label:memory, build",
    "review",
    "spec",
    "build, web/**",
    "docs/*.md",
    "Cargo.toml",
    "review, crates/core/src/memory.rs",
]
SCOPE_SENTENCE = (
    "scope names core, archive, spec, build, review, label:<name> or a path glob, "
    "separated by commas"
)


@pytest.mark.parametrize("scope", REFUSED)
def test_a_scope_term_that_is_neither_role_nor_glob_is_refused(scope: str) -> None:
    assert scope_refusal(entry(scope=scope)) == SCOPE_SENTENCE


@pytest.mark.parametrize("scope", ALLOWED)
def test_the_allowed_scopes_are_not_refused(scope: str) -> None:
    assert scope_refusal(entry(scope=scope)) is None


@pytest.mark.parametrize("scope", ["archive, build", "core, archive", "docs/*.md, archive"])
def test_archive_stands_alone_in_a_scope(scope: str) -> None:
    assert scope_refusal(entry(scope=scope)) == (
        "archive is a scope of its own: it combines with no other term"
    )


def test_archive_alone_and_a_label_beside_a_role_are_not_refused() -> None:
    assert scope_refusal(entry(scope="archive")) is None
    assert scope_refusal(entry(scope="label:web, build")) is None


@pytest.mark.parametrize(
    ("term", "glob"),
    [("web/**", True), ("a*", True), ("a?", True), ("[ab]", True), ("Cargo.toml", True),
     ("build", False), ("core", False), ("label:a.b", False)],
)  # fmt: skip
def test_a_term_is_a_glob_unless_it_is_a_label_or_holds_none_of_the_marks(
    term: str, glob: bool
) -> None:
    assert is_glob(term) is glob


def test_everywhere_is_an_empty_scope_or_core() -> None:
    assert everywhere(entry(scope=""))
    assert everywhere(entry(scope="  "))
    assert everywhere(entry(scope="core"))
    assert not everywhere(entry(scope="build"))
    assert everywhere(entry(scope="web/**, core, build"))


def test_core_and_archived_are_read_from_the_terms() -> None:
    assert is_core(entry(scope="build, core"))
    assert not is_core(entry(scope="corex"))
    assert is_archived(entry(scope="archive"))
    assert not is_archived(entry(scope="build"))


def test_a_role_scope_applies_to_its_own_stage_only() -> None:
    scoped = entry(scope="build, review")
    assert for_role(scoped, "build")
    assert for_role(scoped, "review")
    assert not for_role(scoped, "spec")


def test_a_stage_outside_the_roles_is_not_a_role_even_when_the_scope_names_it() -> None:
    assert not for_role(entry(scope="merge"), "merge")
    assert not for_role(entry(scope="build"), "")


def test_a_label_term_applies_to_a_ticket_carrying_the_label() -> None:
    scoped = entry(scope="label:memory, build")
    assert for_labels(scoped, ("memory",))
    assert not for_labels(scoped, ("web",))
    assert not for_labels(scoped, ())
    assert not for_labels(entry(scope="memory"), ("memory",))


def test_a_glob_touches_a_path_and_star_crosses_folders() -> None:
    scoped = entry(scope="docs/*.md, web/**")
    assert touches(scoped, ["docs/a/b.md"])
    assert touches(scoped, ["x", "web/src/app.vue"])
    assert not touches(scoped, ["src/docs.md", "README.md"])
    assert not touches(entry(scope="build"), ["build"])


@pytest.mark.parametrize(
    ("scope", "words"),
    [
        ("", "every session"),
        ("core", "every session, first"),
        ("archive", "searched on demand, listed in the index"),
        ("label:memory", "tickets labelled memory"),
        ("web/**", "sessions changing web/**"),
        ("build", "build runs"),
        (
            "review, label:a, src/x.py",
            "review runs; tickets labelled a; sessions changing src/x.py",
        ),
    ],
)  # fmt: skip
def test_the_page_says_where_each_entry_loads(scope: str, words: str) -> None:
    assert loads(entry(scope=scope)) == words


def test_fields_name_the_scope_refusal_after_the_other_checks() -> None:
    assert check_fields("rule", "Scoped", entry(scope="bulid")) == SCOPE_SENTENCE
