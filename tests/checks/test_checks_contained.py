"""A sandboxed run goes through srt: a stand-in script records what it was given."""

import os
from pathlib import Path

import pytest

from checks_support import FakeSandbox, script, write_config
from code_factory.checks.models import Verdict
from code_factory.checks.service import CheckOptions, CheckService
from code_factory.tickets.models import Ticket

SANDBOXED = "[checks]\ncommand = 'echo ran > {out}/ran'\n"
BASE = {
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM", "LANG", "LC_ALL", "LC_CTYPE",
    "TZ",
}  # fmt: skip


@pytest.fixture
def out(tmp_path: Path) -> Path:
    folder = tmp_path / "out"
    folder.mkdir()
    return folder


@pytest.fixture
def srt(tmp_path: Path, out: Path) -> Path:
    """Records its arguments, its environment and the settings file, then runs the command."""
    return script(
        tmp_path / "bin" / "srt",
        f'printf "%s\\n" "$@" > {out}/argv\nenv > {out}/env\ncat "$2" > {out}/settings\n'
        'exec /bin/sh -c "$4"',
    )


@pytest.fixture
def options(state: Path, srt: Path) -> CheckOptions:
    return CheckOptions(
        state_dir=state, heartbeat_s=3600.0, turn_poll_s=0.01, shutdown_s=1.0, program=str(srt)
    )


async def test_the_command_runs_inside_srt_with_the_rules_the_port_gave_and_only_the_base_env(
    checks: CheckService, started: Ticket, root: Path, out: Path
) -> None:
    write_config(root, SANDBOXED.format(out=out))
    check_id = await checks.start(started.id)
    row = await checks.run_now(check_id)

    assert row.verdict is Verdict.PASSED
    assert (out / "ran").read_text() == "ran\n"
    argv = (out / "argv").read_text().splitlines()
    assert argv[0] == "--settings"
    assert argv[1].endswith(".sandbox.json")
    assert argv[2:] == ["-c", f"echo ran > {out}/ran"]
    assert (out / "settings").read_text() == '{"kind": "tree"}'
    names = {line.split("=", 1)[0] for line in (out / "env").read_text().splitlines()}
    assert names - {"PWD", "SHLVL", "_", "OLDPWD"} == BASE & names | {
        "CLAUDE_CODE_TMPDIR",
        "XDG_RUNTIME_DIR",
        "CODE_FACTORY_OFFLINE",
    }
    assert "CODE_FACTORY_OFFLINE=1" in (out / "env").read_text().splitlines()
    assert os.environ["CODE_FACTORY_DATABASE_URL"] not in (out / "env").read_text()


async def test_the_settings_file_is_removed_after_the_run(
    checks: CheckService, started: Ticket, root: Path, out: Path, state: Path
) -> None:
    write_config(root, SANDBOXED.format(out=out))
    await checks.run_now(await checks.start(started.id))
    assert list((state / "checks").glob("*.sandbox.json")) == []


async def test_a_port_that_refuses_runs_nothing_and_the_log_says_why(
    checks: CheckService,
    sandbox: FakeSandbox,
    started: Ticket,
    root: Path,
    out: Path,
) -> None:
    sandbox.refuse = "the sandbox rules cannot be made: no key is named"
    write_config(root, SANDBOXED.format(out=out))
    row = await checks.run_now(await checks.start(started.id))
    assert (row.verdict, row.exit_code) == (Verdict.NO_VERDICT, -1)
    assert Path(row.log_path).read_text() == "the sandbox rules cannot be made: no key is named\n"
    assert not (out / "ran").exists()


async def test_a_missing_srt_runs_nothing_and_says_how_to_install_or_switch_off(
    checks: CheckService, started: Ticket, root: Path, out: Path, srt: Path
) -> None:
    srt.unlink()
    write_config(root, SANDBOXED.format(out=out))
    row = await checks.run_now(await checks.start(started.id))
    assert row.exit_code == -1
    assert Path(row.log_path).read_text() == (
        "the checks run inside srt (@anthropic-ai/sandbox-runtime), which is not installed; "
        "install it, or set [agents] sandbox = false in .code-factory/config.toml\n"
    )


async def test_with_the_sandbox_off_no_srt_is_started(
    checks: CheckService, started: Ticket, root: Path, out: Path
) -> None:
    write_config(root, SANDBOXED.format(out=out) + "[agents]\nsandbox = false\n")
    row = await checks.run_now(await checks.start(started.id))
    assert row.verdict is Verdict.PASSED
    assert (out / "ran").exists()
    assert not (out / "argv").exists()
