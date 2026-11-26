"""More defects a second reading found, at the service: a tracked file that cannot be read, a Slack
grant, the real home folder, an uncommitted change, an oversize lockfile and a linked worktree."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.settings.models.problems import ReviewGuide
from code_factory.settings.service import SettingsService
from settings_support import agit, arepository, write

CONFIG = ".code-factory/config.toml"
EXCEPTIONS = ".code-factory/exceptions.toml"
UNREADABLE = "is not a text file of at most {} KiB below the repository (a link is not followed)"
EXPIRED = (
    '[[advisory]]\nid = "A"\nfile = "deny.toml"\nreason = "r"\nticket = "CF-1"\n'
    "expires = 2000-01-01\n"
)


class Tickets:
    async def existing(self, ids):  # noqa: ANN001, ANN201
        return frozenset(ids)

    async def sharing_branch(self, ticket_id: str) -> tuple[str, ...]:  # noqa: ARG002
        return ()


@pytest.fixture
def service(uow: UnitOfWork) -> SettingsService:
    found = SettingsService(
        uow, clock=lambda: datetime(2026, 11, 2, tzinfo=UTC), home=Path("/Users/alex")
    )
    found.bind_ticket_facts(Tickets())
    return found


async def test_a_tracked_tool_file_that_cannot_be_read_is_a_problem(
    service: SettingsService, tmp_path: Path
) -> None:
    root = await arepository(tmp_path / "r", {"real.toml": "[advisories]\nignore = []\n"})
    (root / "deny.toml").symlink_to(root / "real.toml")
    write(root, "web/pnpm-workspace.yaml", "#" * (256 * 1024 + 1))
    await agit(root, "add", "-A")
    report = await service.check_exceptions(root)
    assert [str(p) for p in report.problems] == [
        "deny.toml:0: " + UNREADABLE.format(256),
        "web/pnpm-workspace.yaml:0: " + UNREADABLE.format(256),
    ]


async def test_a_slack_key_held_for_another_repository_is_named(
    service: SettingsService, tmp_path: Path
) -> None:
    write(
        tmp_path,
        CONFIG,
        '[intake]\nslack_channel = "C1"\nslack_token_env = "CODE_FACTORY_INTAKE_SLACK"\n',
    )
    await service.grant_intake_key(
        "CODE_FACTORY_INTAKE_SLACK", Path("/elsewhere"), "https://slack.com/api"
    )
    report = await service.check_config(tmp_path)
    assert [str(p) for p in report.problems] == [
        (
            ".code-factory/config.toml:3: intake.slack_token_env: "
            "CODE_FACTORY_INTAKE_SLACK is held "
            "on this machine for /elsewhere at https://slack.com/api"
        )
    ]
    await service.grant_intake_key("CODE_FACTORY_INTAKE_SLACK", tmp_path, "https://slack.com/api/")
    assert (await service.check_config(tmp_path)).problems == ()


async def test_the_service_checks_mounts_against_the_home_it_was_given(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, CONFIG, '[checks]\ncontainer_mounts = ["/Users/alex/.aws:/aws"]\n')
    (problem,) = (await service.check_config(tmp_path)).problems
    assert problem.line == 2
    assert "holds or is in the home folder or a secret folder" in problem.message


async def test_an_uncommitted_edit_of_a_watched_file_counts_as_a_change(
    service: SettingsService, tmp_path: Path
) -> None:
    root = await arepository(
        tmp_path / "r",
        {"deny.toml": '[advisories]\nignore = ["A"]\n', EXCEPTIONS: EXPIRED, "src/a.py": "a\n"},
    )
    await agit(root, "commit", "-q", "-m", "main")
    await agit(root, "checkout", "-q", "-b", "feature")
    write(root, "src/a.py", "b\n")
    await agit(root, "commit", "-q", "-am", "unrelated")
    assert (await service.check_exceptions(root)).problems == ()
    write(root, EXCEPTIONS, EXPIRED + "# edited, not committed\n")
    report = await service.check_exceptions(root)
    assert [p.message for p in report.problems] == ["A expired on 2000-01-01"]


async def test_a_lockfile_past_the_yaml_cap_is_reported_as_unreadable_not_as_missing_the_package(
    service: SettingsService, tmp_path: Path
) -> None:
    entry = (
        '[[age]]\npackage = "left-pad@1.3.0"\nlockfile = "web/pnpm-lock.yaml"\nreason = "r"\n'
        'chosen = 2026-11-02\nticket = "CF-1"\nexpires = 2999-12-31\n'
    )
    root = await arepository(
        tmp_path / "r",
        {
            EXCEPTIONS: entry,
            "web/pnpm-lock.yaml": "#" * (2 * 1024 * 1024 + 1),
            "web/pnpm-workspace.yaml": "minimumReleaseAgeExclude:\n  - left-pad@1.3.0\n",
        },
    )
    report = await service.check_exceptions(root)
    assert [str(p) for p in report.problems] == [
        ".code-factory/exceptions.toml:2: web/pnpm-lock.yaml " + UNREADABLE.format(2048)
    ]


async def test_a_lockfile_that_is_not_yaml_is_named_once(
    service: SettingsService, tmp_path: Path
) -> None:
    entry = (
        '[[age]]\npackage = "left-pad@1.3.0"\nlockfile = "web/pnpm-lock.yaml"\nreason = "r"\n'
        'chosen = 2026-11-02\nticket = "CF-1"\nexpires = 2999-12-31\n'
    )
    root = await arepository(
        tmp_path / "r",
        {
            EXCEPTIONS: entry,
            "web/pnpm-lock.yaml": "a: [1\n",
            "web/pnpm-workspace.yaml": "minimumReleaseAgeExclude:\n  - left-pad@1.3.0\n",
        },
    )
    report = await service.check_exceptions(root)
    assert [str(p) for p in report.problems] == [
        "web/pnpm-lock.yaml:0: yaml: not valid YAML, or too large to read"
    ]


async def test_the_effective_config_is_the_main_checkouts_not_a_worktrees(
    service: SettingsService, tmp_path: Path
) -> None:
    root = await arepository(tmp_path / "main", {CONFIG: '[checks]\ncommand = "main"\n'})
    await agit(root, "commit", "-q", "-m", "c")
    linked = tmp_path / "linked"
    await agit(root, "worktree", "add", "-q", "-b", "wt", str(linked))
    write(linked, CONFIG, '[checks]\ncommand = "branch"\n')
    assert await service.main_checkout(linked) == root.resolve()
    checks = (await service.load(await service.main_checkout(linked))).checks
    assert checks is not None
    assert checks.command == "main"
    assert await service.repository_root(linked) == linked.resolve()


GUIDE = ".code-factory/REVIEW.md"


async def test_the_review_guide_is_the_base_branchs_text_stripped_with_its_name(
    service: SettingsService, tmp_path: Path
) -> None:
    root = await arepository(tmp_path / "r", {GUIDE: "\n  Check the parser.\nSkip web/dist.\n\n"})
    await agit(root, "commit", "-q", "-m", "main")
    guide = await service.review_guide(root)
    assert guide == ReviewGuide(base="main", text="Check the parser.\nSkip web/dist.")


async def test_a_guide_edited_on_the_branch_or_uncommitted_is_not_read(
    service: SettingsService, tmp_path: Path
) -> None:
    root = await arepository(tmp_path / "r", {GUIDE: "main's guide\n"})
    await agit(root, "commit", "-q", "-m", "main")
    await agit(root, "checkout", "-q", "-b", "feature")
    write(root, GUIDE, "the branch's guide\n")
    await agit(root, "commit", "-q", "-am", "edit")
    write(root, GUIDE, "an uncommitted guide\n")
    assert await service.review_guide(root) == ReviewGuide(base="main", text="main's guide")


async def test_no_guide_an_empty_one_or_no_repository_reads_none(
    service: SettingsService, tmp_path: Path
) -> None:
    none = await arepository(tmp_path / "none", {"a": "a\n"})
    await agit(none, "commit", "-q", "-m", "main")
    blank = await arepository(tmp_path / "blank", {GUIDE: " \n\t\n"})
    await agit(blank, "commit", "-q", "-m", "main")
    outside = tmp_path / "outside"
    outside.mkdir()
    assert [await service.review_guide(r) for r in (none, blank, outside)] == [None, None, None]
