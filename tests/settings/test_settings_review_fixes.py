"""Defects a second reading of the module found, each pinned by the input that broke it: a
decimal past Python's digit limit, a NUL in a path, a header with a trailing comment, a deeply
nested YAML document, a tracker address with a bad port, and a quadratic scan on a cache miss."""

import threading
from datetime import date
from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.settings import service as service_module
from code_factory.settings.adapters import Files, lock_packages, scanning, workspace_lists
from code_factory.settings.rules import (
    ExceptionFacts,
    config_problems,
    exceptions_problems,
    lenient_config,
    parse_toml,
    tracker_allowed,
)
from code_factory.settings.rules import cross as cross_module
from code_factory.settings.rules.lines import entry_line, header_line, key_line
from code_factory.settings.rules.tool_files import deny_ignores
from code_factory.settings.service import SettingsService
from code_factory.settings.service import checks as checks_module
from settings_support import agit, arepository, write

HUGE = "9" * 5000


def test_an_integer_past_the_digit_limit_is_a_toml_error_not_an_exception() -> None:
    text = f"[checks]\ntimeout = {HUGE}\n"
    assert parse_toml(text).__class__.__name__ == "TomlError"
    assert [p.message.startswith("toml: ") for p in config_problems("c", text)] == [True]
    assert lenient_config(text).model_dump(exclude_none=True) == {}
    found = deny_ignores(f"[advisories]\nx = {HUGE}\n")
    assert isinstance(found, str)
    assert found.startswith("toml: ")


def test_a_header_with_a_trailing_comment_is_still_a_header() -> None:
    text = '[agents] # how runs are made\nreview = true\n\n[[automations]] # one\nname = "a"\n'
    assert key_line(text, "agents", "review") == 2
    assert header_line(text, "automations") == 4
    assert entry_line(text, "automations", 0, "name") == 5


def test_a_quarantine_entry_with_a_commented_header_keeps_its_line_shapes() -> None:
    text = (
        '[[quarantine]] # flaky on CI\ntest = "tests/test_a.py::test_x"\nreason = "r"\n'
        'ticket = "CF-1"\nexpires = 2999-12-31\n'
    )
    facts = ExceptionFacts(
        tickets=frozenset({"CF-1"}), expiry_fails=True, tests={"tests/test_a.py::test_x": True}
    )
    assert exceptions_problems(text, date(2026, 11, 2), facts).problems == ()


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("https://api.linear.app:443/graphql", True),
        ("https://api.linear.app:65535/graphql", True),
        ("https://api.linear.app:abc/graphql", False),
        ("https://api.linear.app:0/graphql", False),
        ("https://api.linear.app:65536/graphql", False),
        ("https://api.linear.app:/graphql", False),
        ("http://localhost:99999", False),
        ("http://localhost:4100", True),
    ],
)
def test_a_tracker_address_with_a_bad_port_is_refused(address: str, expected: bool) -> None:
    assert tracker_allowed("linear", address) is expected


def test_unique_automation_names_cost_no_line_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "".join(
        f'[[automations]]\nname = "n{i}"\nevery = "day"\ntitle = "t"\n\n' for i in range(300)
    )
    scans = []
    real = cross_module.entry_line
    monkeypatch.setattr(cross_module, "entry_line", lambda *a: scans.append(a) or real(*a))
    assert len(lenient_config(text).automations or []) == 300
    assert scans == []


async def test_a_path_with_a_nul_reads_as_missing(tmp_path: Path) -> None:
    files = Files()
    (tmp_path / "a").write_text("x")
    assert await files.read_below(tmp_path, "a\0b", 100) is None
    assert await files.stat(tmp_path, "a\0b") is None
    assert await files.present(tmp_path, "a\0b") is False
    assert await files.names(tmp_path, "a\0b") == []


async def test_a_template_path_with_a_nul_is_a_problem_not_an_exception(
    uow: UnitOfWork, tmp_path: Path
) -> None:
    config = tmp_path / ".code-factory" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '[[automations]]\nname = "a"\nevery = "day"\ntitle = "t"\ntemplate = "a\\u0000b.md"\n'
    )
    report = await SettingsService(uow).check_config(tmp_path)
    assert [p.line for p in report.problems] == [5]
    assert "is not a text file" in report.problems[0].message


async def test_a_deeply_nested_yaml_document_is_unreadable_not_an_exception() -> None:
    deep = "a: " + "[" * 50_000 + "]" * 50_000
    assert await workspace_lists(deep) is None
    assert await lock_packages(deep) is None


async def test_the_config_is_parsed_off_the_event_loop(
    uow: UnitOfWork, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    real = service_module.loaded_config

    def spy(text: str, *rest: object):  # noqa: ANN202
        seen.append(threading.current_thread().name)
        return real(text, *rest)  # ty: ignore[invalid-argument-type]  # the homes, as given

    monkeypatch.setattr(service_module, "loaded_config", spy)
    config = tmp_path / ".code-factory" / "config.toml"
    config.parent.mkdir()
    config.write_text('[checks]\ncommand = "x"\n')
    loaded = await SettingsService(uow).load(tmp_path)
    assert loaded.checks is not None
    assert seen
    assert seen[0] != threading.main_thread().name


EXCEPTIONS = ".code-factory/exceptions.toml"


class Tickets:
    async def existing(self, ids):  # noqa: ANN001, ANN201
        return frozenset(ids)

    async def sharing_branch(self, ticket_id: str) -> tuple[str, ...]:  # noqa: ARG002
        return ()


UNREADABLE_EXCEPTIONS = (
    ".code-factory/exceptions.toml:0: is not a text file of at most 256 KiB below the repository "
    "(a link is not followed)"
)
EXPIRED_ENTRY = (
    '[[advisory]]\nid = "A"\nfile = "deny.toml"\nreason = "r"\nticket = "CF-1"\n'
    "expires = 2020-01-01\n"
)


@pytest.mark.parametrize("how", ["not-utf8", "symlink", "oversize"])
async def test_an_exceptions_file_that_cannot_be_read_is_a_problem_not_an_empty_file(
    uow: UnitOfWork, tmp_path: Path, how: str
) -> None:
    folder = tmp_path / ".code-factory"
    folder.mkdir()
    target = folder / "exceptions.toml"
    if how == "not-utf8":
        target.write_bytes(EXPIRED_ENTRY.encode() + b"\xff\n")
    elif how == "oversize":
        target.write_text("#" * (256 * 1024 + 1))
    else:
        (tmp_path / "real.toml").write_text(EXPIRED_ENTRY)
        target.symlink_to(tmp_path / "real.toml")
    service = SettingsService(uow)
    for report in (
        await service.check_exceptions(tmp_path),
        await service.check_repository(tmp_path),
    ):
        assert [str(p) for p in report.problems] == [UNREADABLE_EXCEPTIONS]


async def test_an_absent_exceptions_file_is_still_no_problem(
    uow: UnitOfWork, tmp_path: Path
) -> None:
    assert (await SettingsService(uow).check_exceptions(tmp_path)).problems == ()


async def test_a_config_check_parses_and_scans_off_the_event_loop(
    uow: UnitOfWork, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    threads: dict[str, str] = {}

    def spied(name: str):  # noqa: ANN202
        owner = scanning if name in {"config_problems", "automation_templates"} else checks_module
        real = getattr(owner, name)

        def spy(*args: object):  # noqa: ANN202
            threads[name] = threading.current_thread().name
            return real(*args)

        monkeypatch.setattr(owner, name, spy)

    for name in (
        "config_problems",
        "lenient_config",
        "automation_templates",
        "intake_key_problems",
    ):
        spied(name)
    config = tmp_path / ".code-factory" / "config.toml"
    config.parent.mkdir()
    config.write_text('[intake]\nlinear_label = "x"\nlinear_token_env = "CODE_FACTORY_INTAKE_L"\n')
    service = SettingsService(uow)
    await service.grant_intake_key(
        "CODE_FACTORY_INTAKE_L", Path("/elsewhere"), "https://api.linear.app/graphql"
    )
    await service.check_config(tmp_path)
    main = threading.main_thread().name
    assert set(threads) == {
        "config_problems",
        "lenient_config",
        "automation_templates",
        "intake_key_problems",
    }
    assert {name: thread for name, thread in threads.items() if thread == main} == {}


async def test_a_config_check_that_times_out_is_a_problem_not_a_pass(
    uow: UnitOfWork, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def times_out(*_: object) -> None:
        return None

    monkeypatch.setattr(checks_module, "in_thread", times_out)
    config = tmp_path / ".code-factory" / "config.toml"
    config.parent.mkdir()
    config.write_text('[checks]\ncommand = "x"\n')
    report = await SettingsService(uow).check_config(tmp_path)
    assert [str(p) for p in report.problems] == [
        ".code-factory/config.toml:0: the check did not finish in time"
    ]


async def test_on_its_expiry_day_an_entry_of_an_unrelated_branch_is_a_note(
    uow: UnitOfWork, tmp_path: Path
) -> None:
    root = await arepository(
        tmp_path / "r",
        {
            "deny.toml": '[advisories]\nignore = ["A"]\n',
            EXCEPTIONS: EXPIRED_ENTRY,
            "src/a.py": "a\n",
        },
    )
    await agit(root, "commit", "-q", "-m", "main")
    await agit(root, "checkout", "-q", "-b", "feature")
    write(root, "src/a.py", "b\n")
    await agit(root, "commit", "-q", "-am", "unrelated")
    service = SettingsService(uow)
    service.bind_ticket_facts(Tickets())
    on_the_day = await service.check_exceptions(root, today=date(2020, 1, 1))
    assert (on_the_day.problems, [p.message for p in on_the_day.notes]) == (
        (),
        ["A expired on 2020-01-01; main's own run fails on it"],
    )
    day_before = await service.check_exceptions(root, today=date(2019, 12, 31))
    assert (day_before.problems, day_before.notes) == ((), ())
