"""`check_config` and `check_repository` over folders in `tmp_path`: the report is `path:line:
message`, sorted by path and line. Cases and messages come from the previous implementation's
`config_keys.rs` (automation templates) and `validate.rs` (intake keys held for another site)."""

from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.settings.service import SettingsService
from settings_support import write

CONFIG = ".code-factory/config.toml"
TEMPLATES = (
    '[[automations]]\nname = "a"\nevery = "day"\ntitle = "t"\ntemplate = "t/there.md"\n\n'
    '[[automations]]\nname = "b"\nevery = "day"\ntitle = "t"\ntemplate = "t/missing.md"\n\n'
    '[[automations]]\nname = "c"\nevery = "day"\ntitle = "t"\ntemplate = "t/link.md"\n'
)
JIRA_CONFIG = (
    '[intake]\njira_url = "https://acme.atlassian.net"\njira_jql = "project = ENG"\n'
    'jira_email = "bot@acme.example"\njira_token_env = "CODE_FACTORY_INTAKE_JIRA"\n'
    'linear_label = "x"\nlinear_token_env = "CODE_FACTORY_INTAKE_LINEAR"\n'
)
JIRA = "CODE_FACTORY_INTAKE_JIRA"
LINEAR = "CODE_FACTORY_INTAKE_LINEAR"


@pytest.fixture
def service(uow: UnitOfWork) -> SettingsService:
    return SettingsService(uow)


async def config_lines(service: SettingsService, root: Path) -> list[str]:
    return [str(p) for p in (await service.check_config(root)).problems]


async def test_a_repository_without_a_config_has_no_problem(
    service: SettingsService, tmp_path: Path
) -> None:
    assert await config_lines(service, tmp_path) == []


async def test_problems_name_the_file_the_line_and_the_message(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, CONFIG, '[checks]\ncommand = "true"\ntimeout = "ten"\n')
    assert await config_lines(service, tmp_path) == [
        ".code-factory/config.toml:3: checks.timeout: expected a positive integer"
    ]


async def test_a_toml_syntax_error_is_one_problem_with_its_line(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, CONFIG, '[checks]\ncommand = "a"\ncommand = "b"\n')
    (only,) = await config_lines(service, tmp_path)
    assert only.startswith(".code-factory/config.toml:3: toml: ")


async def test_a_config_that_is_a_link_or_too_big_is_a_problem_not_silence(
    service: SettingsService, tmp_path: Path
) -> None:
    unreadable = (
        ".code-factory/config.toml:0: is not a text file of at most 256 KiB below the "
        "repository (a link is not followed)"
    )
    (tmp_path / ".code-factory").mkdir()
    (tmp_path / "real.toml").write_text('[checks]\ncommand = "x"\n')
    (tmp_path / CONFIG).symlink_to(tmp_path / "real.toml")
    assert await config_lines(service, tmp_path) == [unreadable]
    big = tmp_path / "big"
    write(big, CONFIG, "#" * (256 * 1024 + 1))
    assert await config_lines(service, big) == [unreadable]


async def test_an_automation_template_that_cannot_be_read_is_refused_on_its_line(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, CONFIG, TEMPLATES)
    write(tmp_path, "t/there.md", "text")
    write(tmp_path, "elsewhere.md", "text")
    (tmp_path / "t" / "link.md").symlink_to(tmp_path / "elsewhere.md")
    refused = (
        '.code-factory/config.toml:{}: automations.template: "{}" is not a text file of at most '
        "64 KiB below the repository (a link is not followed)"
    )
    assert await config_lines(service, tmp_path) == [
        refused.format(11, "t/missing.md"),
        refused.format(17, "t/link.md"),
    ]


async def test_readable_automation_templates_are_accepted(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, CONFIG, TEMPLATES)
    for name in ("there", "missing", "link"):
        write(tmp_path, f"t/{name}.md", "text")
    assert await config_lines(service, tmp_path) == []


async def test_a_template_outside_the_repository_is_the_models_problem_and_is_not_opened(
    service: SettingsService, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    write(
        repo,
        CONFIG,
        '[[automations]]\nname = "a"\nevery = "day"\ntitle = "t"\ntemplate = "../x.md"\n',
    )
    write(tmp_path, "x.md", "text")
    assert await config_lines(service, repo) == [
        ".code-factory/config.toml:5: automations.template: expected a path inside the repository"
    ]


async def test_an_intake_key_held_for_another_repository_or_site_is_named(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, CONFIG, JIRA_CONFIG)
    await service.grant_intake_key(LINEAR, tmp_path, "https://api.linear.app/graphql")
    await service.grant_intake_key(JIRA, Path("/elsewhere/victim"), "https://acme.atlassian.net")
    assert await config_lines(service, tmp_path) == [
        (
            ".code-factory/config.toml:5: intake.jira_token_env: CODE_FACTORY_INTAKE_JIRA is held "
            "on this machine for /elsewhere/victim at https://acme.atlassian.net"
        )
    ]
    await service.grant_intake_key(JIRA, tmp_path, "https://victim.atlassian.net")
    assert await config_lines(service, tmp_path) == [
        (
            ".code-factory/config.toml:5: intake.jira_token_env: CODE_FACTORY_INTAKE_JIRA is held "
            f"on this machine for {tmp_path} at https://victim.atlassian.net"
        )
    ]


async def test_a_key_held_for_this_repository_and_address_passes(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, CONFIG, JIRA_CONFIG)
    await service.grant_intake_key(LINEAR, tmp_path, "https://api.linear.app/graphql")
    await service.grant_intake_key(JIRA, tmp_path, "https://acme.atlassian.net/")
    assert await config_lines(service, tmp_path) == []


async def test_check_repository_adds_the_exceptions_and_the_template_files(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, CONFIG, "[checks]\ntimeout = 0\n")
    write(tmp_path, ".code-factory/exceptions.toml", '[[advisory]]\nid = "A"\n')
    write(tmp_path, ".code-factory/templates/ticket-bug.md", "## Steps\n")
    write(tmp_path, ".code-factory/agents/build.md", "ok")
    (tmp_path / ".code-factory/agents/review.md").write_bytes(b"\xff\xfe")
    (tmp_path / ".code-factory/templates/spec.md").write_bytes(b"a" * (64 * 1024 + 1))
    (tmp_path / "outside.md").write_text("x")
    (tmp_path / ".code-factory/templates/uat.md").symlink_to(tmp_path / "outside.md")
    (tmp_path / ".code-factory/templates/notes.txt").write_bytes(b"\xff not a template")
    report = await service.check_repository(tmp_path)
    refused = "is not a text file of at most 64 KiB below the repository (a link is not followed)"
    assert [str(p) for p in report.problems] == [
        ".code-factory/agents/review.md:0: " + refused,
        ".code-factory/config.toml:2: checks.timeout: expected a positive integer",
        ".code-factory/exceptions.toml:1: advisory[0].expires: missing",
        ".code-factory/exceptions.toml:1: advisory[0].file: missing",
        ".code-factory/exceptions.toml:1: advisory[0].reason: missing",
        ".code-factory/exceptions.toml:1: advisory[0].ticket: missing",
        ".code-factory/templates/spec.md:0: " + refused,
        ".code-factory/templates/uat.md:0: " + refused,
    ]
    assert report.unchecked == ("ticket references",)


async def test_check_repository_of_a_clean_repository_is_empty(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, CONFIG, '[checks]\ncommand = "true"\n')
    report = await service.check_repository(tmp_path)
    assert (report.problems, report.notes) == ((), ())
