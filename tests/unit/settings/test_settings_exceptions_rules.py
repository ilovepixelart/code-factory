"""`exceptions.toml` held to its model, to the tool files and lockfiles it speaks for, and to the
date. Inputs are the facts a service resolves; expected messages are copied from the previous
implementation's `validate.rs` assertions (folder name renamed, ticket ids `CF-`)."""

from collections.abc import Sequence
from datetime import date
from typing import Any

import pytest

from code_factory.settings.models.problems import ExceptionsReport
from code_factory.settings.rules import (
    ExceptionFacts,
    Listed,
    ToolFiles,
    exception_tickets,
    exceptions_problems,
    expiry_fails,
)

FILE = ".code-factory/exceptions.toml"
TODAY = date(2026, 11, 2)


def facts(**fields: Any) -> ExceptionFacts:  # noqa: ANN401
    base: dict[str, Any] = {"tickets": frozenset({"CF-1"}), "expiry_fails": True}
    return ExceptionFacts(**{**base, **fields})


def run(text: str, **fields: Any) -> list[tuple[str, int, str]]:  # noqa: ANN401
    report = exceptions_problems(text, TODAY, facts(**fields))
    return sorted((p.path, p.line, p.message) for p in report.problems)


def advisory(id_: str, file: str, ticket: str = "CF-1", expires: str = "2999-12-31") -> str:
    return (
        f'[[advisory]]\nid = "{id_}"\nfile = "{file}"\nreason = "r"\nticket = "{ticket}"\n'
        f"expires = {expires}\n\n"
    )


def age(package: str, lockfile: str, ticket: str = "CF-1") -> str:
    return (
        f'[[age]]\npackage = "{package}"\nlockfile = "{lockfile}"\nreason = "r"\n'
        f'chosen = 2026-11-02\nticket = "{ticket}"\nexpires = 2999-12-31\n\n'
    )


def tools(
    ignores: Sequence[tuple[str, str, int]] = (),
    excludes: Sequence[tuple[str, str, int]] = (),
) -> ToolFiles:
    return ToolFiles(
        ignores=tuple(Listed(f, i, n) for f, i, n in ignores),
        excludes=tuple(Listed(f, i, n) for f, i, n in excludes),
    )


def test_an_absent_file_has_no_problem() -> None:
    assert run("") == []


def test_each_entry_is_held_to_its_model_by_line() -> None:
    text = (
        '[[advisory]]\nid = "GHSA-aaaa-bbbb-cccc"\nfile = "deny.toml"\nreason = "r"\n'
        'ticket = "CF-1"\n\n'
        '[[advisory]]\nid = "GHSA-dddd-eeee-ffff"\nfile = "deny.toml"\nreason = "  "\n'
        'ticket = "CF-1"\nexpires = 2999-12-31\ncolour = "red"\n\n'
        '[[age]]\npackage = "left-pad@1.3.0"\nlockfile = "web/pnpm-lock.yaml"\nreason = "r"\n'
        'chosen = "2026-11-02"\nticket = "CF-9"\nexpires = 2999-12-31T10:00:00\n'
    )
    assert run(text) == [
        (FILE, 1, "advisory[0].expires: missing"),
        (FILE, 10, "advisory[1].reason: blank"),
        (FILE, 13, "advisory[1].colour: unknown field"),
        (FILE, 19, "age[0].chosen: expected a date"),
        (FILE, 20, "age[0].ticket: no ticket CF-9"),
        (FILE, 21, "age[0].expires: expected a date"),
    ]


def test_a_value_of_the_wrong_type_is_named() -> None:
    text = advisory("A", "deny.toml").replace('reason = "r"', "reason = 3")
    assert run(text) == [(FILE, 4, "advisory[0].reason: expected text")]


def test_a_date_is_a_date_and_not_a_text_or_a_datetime() -> None:
    quoted = advisory("A", "deny.toml", expires='"2999-12-31"')
    stamped = advisory("A", "deny.toml", expires="2999-12-31T10:00:00Z")
    assert run(quoted) == [(FILE, 6, "advisory[0].expires: expected a date")]
    assert run(stamped) == [(FILE, 6, "advisory[0].expires: expected a date")]


def test_an_unknown_top_level_table_and_a_list_that_is_no_list_are_named() -> None:
    assert run("[colour]\nx = 1\n") == [(FILE, 1, "colour: unknown table")]
    assert run('advisory = "x"\n') == [(FILE, 0, "advisory: expected a list of tables")]


def test_a_text_that_is_not_toml_is_one_problem() -> None:
    ((path, line, message),) = run("[[advisory]\n")
    assert (path, line, message.startswith("toml: ")) == (FILE, 1, True)


def test_the_tickets_to_ask_the_tickets_module_are_the_nonblank_ones_in_order() -> None:
    text = advisory("A", "d", ticket="CF-2") + age("p@1.0.0", "l", ticket="CF-1")
    text += advisory("B", "d", ticket="  ")
    assert exception_tickets(text) == ("CF-2", "CF-1")


def test_an_unbound_tickets_module_skips_the_ticket_check() -> None:
    assert (
        run(
            advisory("A", "deny.toml", ticket="CF-9"),
            tickets=None,
            tools=tools(ignores=[("deny.toml", "A", 3)]),
        )
        == []
    )


def test_every_ignore_needs_its_entry() -> None:
    found = run(
        advisory("RUSTSEC-2026-0386", "deny.toml"),
        tools=tools(
            ignores=[
                ("deny.toml", "RUSTSEC-2026-0386", 3),
                ("deny.toml", "RUSTSEC-2026-0001", 4),
                ("web/pnpm-workspace.yaml", "RUSTSEC-2026-0386", 6),
            ]
        ),
    )
    assert found == [
        (
            "deny.toml",
            4,
            "advisory ignore RUSTSEC-2026-0001 has no entry in .code-factory/exceptions.toml",
        ),
        (
            "web/pnpm-workspace.yaml",
            6,
            "advisory ignore RUSTSEC-2026-0386 has no entry in .code-factory/exceptions.toml",
        ),
    ]


def test_an_age_entry_is_no_advisory_entry() -> None:
    found = run(
        age("RUSTSEC-2026-0386", "deny.toml"),
        tools=tools(ignores=[("deny.toml", "RUSTSEC-2026-0386", 3)]),
        locked=frozenset({("deny.toml", "RUSTSEC-2026-0386")}),
    )
    assert (
        "deny.toml",
        3,
        "advisory ignore RUSTSEC-2026-0386 has no entry in .code-factory/exceptions.toml",
    ) in found


def test_an_advisory_the_file_no_longer_names_is_named() -> None:
    text = advisory("GHSA-aaaa-bbbb-cccc", "web/pnpm-workspace.yaml")
    assert run(text, tools=tools()) == [
        (FILE, 2, "GHSA-aaaa-bbbb-cccc is not in web/pnpm-workspace.yaml")
    ]
    assert (
        run(text, tools=tools(ignores=[("web/pnpm-workspace.yaml", "GHSA-aaaa-bbbb-cccc", 3)]))
        == []
    )


def test_an_age_exclusion_is_one_exact_version_with_its_entry() -> None:
    excludes = [
        ("web/pnpm-workspace.yaml", "left-pad", 2),
        ("web/pnpm-workspace.yaml", "@scope/*", 3),
        ("web/pnpm-workspace.yaml", "left-pad@1.3.0", 4),
        ("web/pnpm-workspace.yaml", "left-pad@1.3.0 || 1.3.1", 5),
    ]
    found = run(age("left-pad@1.3.0", "other/pnpm-lock.yaml"), tools=tools(excludes=excludes))
    inexact = "minimumReleaseAgeExclude {} is not one exact version <name>@<x.y.z>"
    assert found == [
        (FILE, 2, "left-pad@1.3.0 is not in other/pnpm-lock.yaml"),
        (FILE, 2, "left-pad@1.3.0 is not in other/pnpm-workspace.yaml"),
        ("web/pnpm-workspace.yaml", 2, inexact.format("left-pad")),
        ("web/pnpm-workspace.yaml", 3, inexact.format("@scope/*")),
        (
            "web/pnpm-workspace.yaml",
            4,
            (
                "minimumReleaseAgeExclude left-pad@1.3.0 has no [[age]] entry in "
                ".code-factory/exceptions.toml"
            ),
        ),
        ("web/pnpm-workspace.yaml", 5, inexact.format("left-pad@1.3.0 || 1.3.1")),
    ]


@pytest.mark.parametrize(
    "package",
    ["left-pad@1.3.0", "@scope/pkg@10.20.30", "a@1.0.0-rc.1", "a.b_c~d@0.0.1"],
)
def test_an_exact_version_passes_with_its_entry_lock_and_exclusion(package: str) -> None:
    lock, workspace = "web/pnpm-lock.yaml", "web/pnpm-workspace.yaml"
    assert (
        run(
            age(package, lock),
            tools=tools(excludes=[(workspace, package, 2)]),
            locked=frozenset({(lock, package)}),
        )
        == []
    )


@pytest.mark.parametrize(
    "package",
    ["left-pad", "left-pad@1", "left-pad@1.3", "left-pad@^1.3.0", "@scope/*", "a@1.0.0+b"],
)
def test_an_inexact_exclusion_is_refused(package: str) -> None:
    found = run("", tools=tools(excludes=[("pnpm-workspace.yaml", package, 1)]))
    assert found == [
        (
            "pnpm-workspace.yaml",
            1,
            f"minimumReleaseAgeExclude {package} is not one exact version <name>@<x.y.z>",
        )
    ]


def test_an_age_entry_the_lockfile_no_longer_holds_is_named() -> None:
    entries = (
        age("utoipa-swagger-ui@10.0.2", "Cargo.lock")
        + age("left-pad@1.3.0", "web/pnpm-lock.yaml")
        + age("utoipa-swagger-ui", "Cargo.lock")
    )
    found = run(
        entries,
        tools=tools(excludes=[("web/pnpm-workspace.yaml", "left-pad@1.3.0", 2)]),
        locked=frozenset({("web/pnpm-lock.yaml", "left-pad@1.3.0")}),
    )
    assert found == [
        (FILE, 2, "utoipa-swagger-ui@10.0.2 is not in Cargo.lock"),
        (FILE, 18, "utoipa-swagger-ui is not in Cargo.lock"),
    ]


def test_a_pnpm_age_entry_still_needs_its_workspace_exclusion() -> None:
    lock = "web/pnpm-lock.yaml"
    found = run(
        age("left-pad@1.3.0", lock), tools=tools(), locked=frozenset({(lock, "left-pad@1.3.0")})
    )
    assert found == [(FILE, 2, "left-pad@1.3.0 is not in web/pnpm-workspace.yaml")]


def test_an_age_entry_on_another_tickets_branch_is_named() -> None:
    text = age("utoipa-swagger-ui@10.0.2", "Cargo.lock")
    locked = frozenset({("Cargo.lock", "utoipa-swagger-ui@10.0.2")})
    shared = run(text, locked=locked, sharing={"CF-1": ("CF-2", "CF-3")})
    assert shared == [
        (
            FILE,
            6,
            (
                "CF-1 shares its branch with CF-2: a security fix under the package age lands as "
                "its own ticket"
            ),
        )
    ]
    assert run(text, locked=locked, sharing={"CF-1": ()}) == []


def test_an_entry_ends_on_its_expiry_date_and_not_the_day_before() -> None:
    text = advisory("A", "deny.toml", expires="2026-11-03")
    listed = tools(ignores=[("deny.toml", "A", 3)])
    day_before = exceptions_problems(text, date(2026, 11, 2), facts(tools=listed))
    on_the_day = exceptions_problems(text, date(2026, 11, 3), facts(tools=listed))
    assert day_before.problems == ()
    assert [(p.line, p.message) for p in on_the_day.problems] == [(6, "A expired on 2026-11-03")]


def test_an_expired_entry_is_a_note_where_main_alone_fails_on_it() -> None:
    text = advisory("A", "deny.toml", expires="2000-01-01")
    report: ExceptionsReport = exceptions_problems(
        text, TODAY, facts(tools=tools(ignores=[("deny.toml", "A", 3)]), expiry_fails=False)
    )
    assert report.problems == ()
    assert [(p.path, p.line, p.message) for p in report.notes] == [
        (FILE, 6, "A expired on 2000-01-01; main's own run fails on it")
    ]


@pytest.mark.parametrize(
    ("base", "head", "changed", "fails"),
    [
        (None, "h", ("src/a.py",), True),
        ("b", "b", (), True),
        ("b", "h", None, True),
        ("b", "h", (".code-factory/exceptions.toml",), True),
        ("b", "h", ("deny.toml",), True),
        ("b", "h", ("web/pnpm-workspace.yaml",), True),
        ("b", "h", ("web/pnpm-lock.yaml",), True),
        ("b", "h", ("Cargo.lock",), True),
        ("b", "h", ("uv.lock",), True),
        ("b", "h", ("src/a.py", "docs/uv.lock.md"), False),
        ("b", "h", (), False),
    ],
)
def test_an_expired_entry_fails_on_main_and_on_a_branch_that_changes_what_it_speaks_for(
    base: str | None, head: str | None, changed: tuple[str, ...] | None, fails: bool
) -> None:
    assert expiry_fails(base, head, changed) is fails
