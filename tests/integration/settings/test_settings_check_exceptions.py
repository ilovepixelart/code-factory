"""`check_exceptions` end to end over real git repositories in `tmp_path`: each case is one of the
previous implementation's `validate.rs` exceptions tests (folder name, ticket ids and the ticket
check renamed); expected report lines are copied from its assertions."""

from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.settings.service import SettingsService
from settings_support import agit, arepository, write

EXCEPTIONS = ".code-factory/exceptions.toml"
IGNORES_ONE = '[advisories]\nignore = ["RUSTSEC-2026-0386"]\n'
EXPIRED = (
    '[[advisory]]\nid = "RUSTSEC-2026-0386"\nfile = "deny.toml"\nreason = "r"\nticket = "CF-1"\n'
    "expires = 2000-01-01\n"
)
EXPIRED_LINE = ".code-factory/exceptions.toml:6: RUSTSEC-2026-0386 expired on 2000-01-01"


class Tickets:
    """The tickets module's side: which tickets exist and which share a branch."""

    def __init__(
        self, known: Collection[str] = ("CF-1",), branches: dict[str, str] | None = None
    ) -> None:
        self.known = frozenset(known)
        self.branches = branches or {}

    async def existing(self, ids: Collection[str]) -> frozenset[str]:
        return self.known & frozenset(ids)

    async def sharing_branch(self, ticket_id: str) -> tuple[str, ...]:
        own = self.branches.get(ticket_id)
        return tuple(
            sorted(
                t
                for t, b in self.branches.items()
                if own is not None and b == own and t != ticket_id
            )
        )


@pytest.fixture
def service(uow: UnitOfWork) -> SettingsService:
    found = SettingsService(uow, clock=lambda: datetime(2026, 11, 2, tzinfo=UTC))
    found.bind_ticket_facts(Tickets())
    return found


async def lines(service: SettingsService, root: Path, **kw) -> list[str]:  # noqa: ANN003
    report = await service.check_exceptions(root, **kw)
    return sorted(str(p) for p in report.problems)


def advisory(id_: str, file: str) -> str:
    return (
        f'[[advisory]]\nid = "{id_}"\nfile = "{file}"\nreason = "r"\nticket = "CF-1"\n'
        "expires = 2999-12-31\n\n"
    )


def age(package: str, lockfile: str, ticket: str = "CF-1") -> str:
    return (
        f'[[age]]\npackage = "{package}"\nlockfile = "{lockfile}"\nreason = "r"\n'
        f'chosen = 2026-11-02\nticket = "{ticket}"\nexpires = 2999-12-31\n\n'
    )


def cargo_lock(version: str) -> str:
    return f'version = 4\n\n[[package]]\nname = "utoipa-swagger-ui"\nversion = "{version}"\n'


def pnpm_lock(version: str) -> str:
    return (
        "---\nlockfileVersion: '9.0'\n\npackages:\n\n  '@pnpm/exe@12.14.0':\n"
        "    resolution: {integrity: x}\n\n---\nlockfileVersion: '9.0'\n\npackages:\n\n"
        f"  left-pad@{version}:\n    resolution: {{integrity: y}}\n"
    )


async def test_a_repository_with_no_exceptions_file_is_clean(
    service: SettingsService, tmp_path: Path
) -> None:
    root = await arepository(tmp_path / "r", {"a.txt": "a"})
    report = await service.check_exceptions(root)
    assert (report.problems, report.notes) == ((), ())


async def test_every_cargo_deny_ignore_needs_its_entry(
    service: SettingsService, tmp_path: Path
) -> None:
    deny = (
        '[advisories]\nignore = [\n    "RUSTSEC-2026-0386",\n'
        '    { id = "RUSTSEC-2026-0001", reason = "r" },\n'
        '    { crate = "foo@1.0.0", reason = "r" },\n]\n'
    )
    root = await arepository(tmp_path / "r", {"deny.toml": deny})
    missing = "advisory ignore {} has no entry in .code-factory/exceptions.toml"
    assert await lines(service, root) == [
        f"deny.toml:3: {missing.format('RUSTSEC-2026-0386')}",
        f"deny.toml:4: {missing.format('RUSTSEC-2026-0001')}",
        f"deny.toml:5: {missing.format('foo@1.0.0')}",
    ]
    write(root, EXCEPTIONS, age("RUSTSEC-2026-0386", "deny.toml"))
    assert f"deny.toml:3: {missing.format('RUSTSEC-2026-0386')}" in await lines(service, root)
    write(
        root,
        EXCEPTIONS,
        "".join(
            advisory(i, "deny.toml")
            for i in ("RUSTSEC-2026-0386", "RUSTSEC-2026-0001", "foo@1.0.0")
        ),
    )
    assert await lines(service, root) == []


async def test_every_pnpm_audit_ignore_needs_its_entry_for_the_same_file(
    service: SettingsService, tmp_path: Path
) -> None:
    workspace = (
        "auditConfig:\n  ignoreGhsas:\n    - GHSA-aaaa-bbbb-cccc\naudit:\n  ignore:\n"
        "    - GHSA-dddd-eeee-ffff\n"
    )
    root = await arepository(
        tmp_path / "r",
        {
            "web/pnpm-workspace.yaml": workspace,
            EXCEPTIONS: advisory("GHSA-aaaa-bbbb-cccc", "deny.toml"),
        },
    )
    missing = (
        "web/pnpm-workspace.yaml:{}: advisory ignore {} has no entry in "
        ".code-factory/exceptions.toml"
    )
    assert await lines(service, root) == [
        ".code-factory/exceptions.toml:2: GHSA-aaaa-bbbb-cccc is not in deny.toml",
        missing.format(3, "GHSA-aaaa-bbbb-cccc"),
        missing.format(6, "GHSA-dddd-eeee-ffff"),
    ]
    write(
        root,
        EXCEPTIONS,
        "".join(
            advisory(i, "web/pnpm-workspace.yaml")
            for i in ("GHSA-aaaa-bbbb-cccc", "GHSA-dddd-eeee-ffff")
        ),
    )
    assert await lines(service, root) == []


async def test_each_entry_is_held_to_its_model_and_its_ticket_is_asked_of_the_tickets_module(
    service: SettingsService, tmp_path: Path
) -> None:
    text = (
        '[[advisory]]\nid = "GHSA-aaaa-bbbb-cccc"\nfile = "deny.toml"\nreason = "r"\n'
        'ticket = "CF-1"\n\n'
        '[[advisory]]\nid = "GHSA-dddd-eeee-ffff"\nfile = "deny.toml"\nreason = "  "\n'
        'ticket = "CF-1"\nexpires = 2999-12-31\ncolour = "red"\n\n'
        '[[age]]\npackage = "left-pad@1.3.0"\nlockfile = "web/pnpm-lock.yaml"\nreason = "r"\n'
        'chosen = "2026-11-02"\nticket = "CF-9"\nexpires = 2999-12-31T10:00:00\n'
    )
    root = await arepository(tmp_path / "r", {EXCEPTIONS: text})
    assert await lines(service, root) == sorted(
        [
            ".code-factory/exceptions.toml:10: advisory[1].reason: blank",
            ".code-factory/exceptions.toml:13: advisory[1].colour: unknown field",
            ".code-factory/exceptions.toml:19: age[0].chosen: expected a date",
            ".code-factory/exceptions.toml:1: advisory[0].expires: missing",
            ".code-factory/exceptions.toml:20: age[0].ticket: no ticket CF-9",
            ".code-factory/exceptions.toml:21: age[0].expires: expected a date",
        ]
    )


async def test_without_a_tickets_module_the_ticket_references_are_reported_unchecked(
    uow: UnitOfWork, tmp_path: Path
) -> None:
    service = SettingsService(uow)
    text = advisory("A", "deny.toml").replace("CF-1", "CF-404")
    root = await arepository(
        tmp_path / "r", {EXCEPTIONS: text, "deny.toml": '[advisories]\nignore = ["A"]\n'}
    )
    report = await service.check_exceptions(root)
    assert report.problems == ()
    assert report.unchecked == ("ticket references",)
    service.bind_ticket_facts(Tickets())
    assert (await service.check_exceptions(root)).unchecked == ()


async def test_an_entry_fails_from_its_expiry_date_on_main_s_tree(
    service: SettingsService, tmp_path: Path
) -> None:
    root = await arepository(tmp_path / "r", {"deny.toml": IGNORES_ONE, EXCEPTIONS: EXPIRED})
    assert await lines(service, root) == [EXPIRED_LINE]
    write(root, EXCEPTIONS, EXPIRED.replace("2000-01-01", "2999-12-31"))
    assert await lines(service, root) == []


async def test_the_clock_decides_the_day_an_entry_ends(uow: UnitOfWork, tmp_path: Path) -> None:
    text = EXPIRED.replace("2000-01-01", "2026-11-03")
    root = await arepository(tmp_path / "r", {"deny.toml": IGNORES_ONE, EXCEPTIONS: text})
    for day, expected in ((2, 0), (3, 1), (4, 1)):
        service = SettingsService(
            uow, clock=lambda day=day: datetime(2026, 11, day, 23, 59, tzinfo=UTC)
        )
        service.bind_ticket_facts(Tickets())
        assert len(await lines(service, root)) == expected, day


async def origin_with_an_expired_entry(tmp_path: Path) -> Path:
    """A work repository whose `main` was pushed to an origin; main holds an expired entry."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    await agit(origin, "init", "-q", "--bare", "-b", "main")
    work = await arepository(
        tmp_path / "work",
        {
            "deny.toml": IGNORES_ONE,
            EXCEPTIONS: EXPIRED,
            "Cargo.lock": "version = 4\n",
            "web/pnpm-workspace.yaml": "minimumReleaseAge: 20160\n",
            "web/pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
            "src/a.rs": "fn a() {}\n",
        },
    )
    await agit(work, "commit", "-q", "-m", "main")
    await agit(work, "remote", "add", "origin", str(origin))
    await agit(work, "push", "-q", "origin", "main")
    return work


async def branch_changing(root: Path, branch: str, path: str, comment: str) -> None:
    await agit(root, "checkout", "-q", "-b", branch, "main")
    text = (root / path).read_text()
    (root / path).write_text(f"{text}{comment} changed\n")
    await agit(root, "commit", "-q", "-am", "change")


@pytest.mark.parametrize(
    ("path", "comment"),
    [
        (EXCEPTIONS, "#"),
        ("deny.toml", "#"),
        ("web/pnpm-workspace.yaml", "#"),
        ("Cargo.lock", "#"),
        ("web/pnpm-lock.yaml", "#"),
    ],
)
async def test_a_branch_changing_what_an_exception_speaks_for_fails_on_an_expired_entry(
    service: SettingsService, tmp_path: Path, path: str, comment: str
) -> None:
    work = await origin_with_an_expired_entry(tmp_path)
    await branch_changing(work, "b", path, comment)
    assert await lines(service, work) == [EXPIRED_LINE]


async def test_a_branch_changing_none_of_them_passes_with_a_note_and_main_still_fails(
    service: SettingsService, tmp_path: Path
) -> None:
    work = await origin_with_an_expired_entry(tmp_path)
    await branch_changing(work, "b", "src/a.rs", "//")
    report = await service.check_exceptions(work)
    assert report.problems == ()
    assert [str(n) for n in report.notes] == [f"{EXPIRED_LINE}; main's own run fails on it"]
    await agit(work, "checkout", "-q", "main")
    assert await lines(service, work) == [EXPIRED_LINE]


async def test_a_named_base_ref_decides_the_fork_point(
    service: SettingsService, tmp_path: Path
) -> None:
    work = await origin_with_an_expired_entry(tmp_path)
    await branch_changing(work, "b", "src/a.rs", "//")
    assert await lines(service, work, base_ref="b") == [EXPIRED_LINE]
    assert await lines(service, work, base_ref="main") == []


async def test_an_age_exclusion_is_one_exact_version_with_its_entry(
    service: SettingsService, tmp_path: Path
) -> None:
    workspace = (
        "minimumReleaseAgeExclude:\n  - left-pad\n  - '@scope/*'\n  - left-pad@1.3.0\n"
        "  - left-pad@1.3.0 || 1.3.1\n"
    )
    root = await arepository(
        tmp_path / "r",
        {
            "web/pnpm-workspace.yaml": workspace,
            EXCEPTIONS: age("left-pad@1.3.0", "other/pnpm-lock.yaml"),
        },
    )
    inexact = (
        "web/pnpm-workspace.yaml:{}: minimumReleaseAgeExclude {} is not one exact version "
        "<name>@<x.y.z>"
    )
    assert await lines(service, root) == sorted(
        [
            ".code-factory/exceptions.toml:2: left-pad@1.3.0 is not in other/pnpm-lock.yaml",
            ".code-factory/exceptions.toml:2: left-pad@1.3.0 is not in other/pnpm-workspace.yaml",
            inexact.format(2, "left-pad"),
            inexact.format(3, "@scope/*"),
            (
                "web/pnpm-workspace.yaml:4: minimumReleaseAgeExclude left-pad@1.3.0 has no [[age]] "
                "entry in .code-factory/exceptions.toml"
            ),
            inexact.format(5, "left-pad@1.3.0 || 1.3.1"),
        ]
    )


async def test_an_age_entry_the_lockfile_no_longer_holds_is_named(
    service: SettingsService, tmp_path: Path
) -> None:
    entries = [
        age("utoipa-swagger-ui@10.0.2", "Cargo.lock"),
        age("left-pad@1.3.0", "web/pnpm-lock.yaml"),
        age("utoipa-swagger-ui", "Cargo.lock"),
    ]
    root = await arepository(
        tmp_path / "r",
        {
            EXCEPTIONS: "".join(entries),
            "Cargo.lock": cargo_lock("10.0.3"),
            "web/pnpm-lock.yaml": pnpm_lock("1.3.1"),
            "web/pnpm-workspace.yaml": "minimumReleaseAgeExclude:\n  - left-pad@1.3.0\n",
        },
    )
    assert await lines(service, root) == [
        ".code-factory/exceptions.toml:10: left-pad@1.3.0 is not in web/pnpm-lock.yaml",
        ".code-factory/exceptions.toml:18: utoipa-swagger-ui is not in Cargo.lock",
        ".code-factory/exceptions.toml:2: utoipa-swagger-ui@10.0.2 is not in Cargo.lock",
    ]
    write(root, EXCEPTIONS, "".join(entries[:2]))
    write(root, "Cargo.lock", cargo_lock("10.0.2"))
    write(root, "web/pnpm-lock.yaml", pnpm_lock("1.3.0"))
    assert await lines(service, root) == []


async def test_an_entry_whose_file_no_longer_names_it_is_named(
    service: SettingsService, tmp_path: Path
) -> None:
    entries = advisory("GHSA-aaaa-bbbb-cccc", "web/pnpm-workspace.yaml") + age(
        "left-pad@1.3.0", "web/pnpm-lock.yaml"
    )
    root = await arepository(
        tmp_path / "r",
        {
            EXCEPTIONS: entries,
            "web/pnpm-lock.yaml": pnpm_lock("1.3.0"),
            "web/pnpm-workspace.yaml": "minimumReleaseAge: 20160\n",
        },
    )
    assert await lines(service, root) == [
        ".code-factory/exceptions.toml:2: GHSA-aaaa-bbbb-cccc is not in web/pnpm-workspace.yaml",
        ".code-factory/exceptions.toml:9: left-pad@1.3.0 is not in web/pnpm-workspace.yaml",
    ]


async def test_a_fix_under_the_package_age_is_on_a_branch_of_its_own_ticket(
    uow: UnitOfWork, tmp_path: Path
) -> None:
    root = await arepository(
        tmp_path / "r",
        {
            EXCEPTIONS: age("utoipa-swagger-ui@10.0.2", "Cargo.lock"),
            "Cargo.lock": cargo_lock("10.0.2"),
        },
    )
    service = SettingsService(uow)
    service.bind_ticket_facts(
        Tickets(["CF-1", "CF-2"], {"CF-1": "ticket/cf-2", "CF-2": "ticket/cf-2"})
    )
    assert await lines(service, root) == [
        (
            ".code-factory/exceptions.toml:6: CF-1 shares its branch with CF-2: a security fix "
            "under "
            "the package age lands as its own ticket"
        )
    ]
    service.bind_ticket_facts(
        Tickets(["CF-1", "CF-2"], {"CF-1": "ticket/cf-2", "CF-2": "ticket/cf-3"})
    )
    assert await lines(service, root) == []


async def test_a_quarantined_test_must_be_defined_in_a_tracked_file(
    service: SettingsService, tmp_path: Path
) -> None:
    entry = '[[quarantine]]\ntest = "{}"\nreason = "r"\nticket = "CF-1"\nexpires = 2999-12-31\n'
    files = {
        "tests/test_a.py": "async def test_flaky() -> None:\n    pass\n",
        "web/src/a.test.ts": "it('shows a card', () => {})\n",
    }
    for test, defined in (
        ("tests/test_a.py::test_flaky", True),
        ("tests/test_a.py::TestX::test_flaky[1]", True),
        ("tests/test_a.py::test_other", False),
        ("tests/test_b.py::test_flaky", False),
        ("web/src/a.test.ts > Board > shows a card", True),
        ("src/a.test.ts > Board > shows a card", True),
        ("web/src/a.test.ts > Board > shows nothing", False),
        ("crate::a::test_flaky", False),
    ):
        root = await arepository(
            tmp_path / test.replace("/", "_").replace(":", "_").replace(" ", "_"),
            {**files, EXCEPTIONS: entry.format(test)},
        )
        found = await lines(service, root)
        expected = (
            []
            if defined
            else [f".code-factory/exceptions.toml:2: {test} names no test in a tracked file"]
        )
        assert found == expected, test
