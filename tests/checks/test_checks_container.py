"""The checks container: a stand-in engine script records what the board asked of it."""

import asyncio
import hashlib
import time
from pathlib import Path

import pytest

from checks_support import REPO, FakeForge, FakeSandbox, container_config, reachable, write_config
from code_factory.agents.service import AgentService
from code_factory.checks.adapters import ContainerChecks, ContainerRun, ContainerSpec, LogFiles
from code_factory.checks.models import RunState, Verdict, ViewState
from code_factory.checks.service import CheckService
from code_factory.git.service import GitService
from code_factory.platform.db import UnitOfWork
from code_factory.tickets.models import Ticket
from code_factory.tickets.service import ActivityService


def containerfile(root: Path) -> None:
    (root / ".code-factory").mkdir(exist_ok=True)
    (root / ".code-factory" / "checks.Containerfile").write_bytes(b"FROM scratch\n")


async def run(checks: CheckService, ticket: Ticket) -> tuple[int, Path]:
    row = await checks.run_now(await checks.start(ticket.id))
    return row.id, Path(row.log_path)


async def test_the_container_gets_its_name_the_tree_read_write_and_the_git_folders_read_only(
    checks: CheckService, started: Ticket, root: Path, out: Path, engine: Path
) -> None:
    write_config(root, container_config(engine))
    check_id, _ = await run(checks, started)
    argv = (out / "run_argv").read_text().splitlines()
    tree = argv[argv.index("--workdir") + 1]
    assert argv[:9] == [
        "run",
        "--rm",
        "--name",
        f"code-factory-check-{check_id}",
        "--network",
        "none",
        "--init",
        "--volume",
        f"{tree}:{tree}:rw",
    ]
    read_only = {a for a in argv if a.endswith(":ro")}
    common = str((root / ".git").resolve())
    admin = f"{common}/worktrees/{Path(tree).name}"
    assert read_only == {f"{common}:{common}:ro", f"{admin}:{admin}:ro"}
    assert argv[-4:] == ["img:1", "/bin/sh", "-c", "true"]
    variables = [argv[i + 1] for i, word in enumerate(argv) if word == "--env"]
    assert "CODE_FACTORY_OFFLINE=1" in variables
    assert not [v for v in variables if v.startswith(("PATH=", "TMPDIR="))]
    assert any(v.startswith("CODE_FACTORY_CHECKS_BASE=") for v in variables)


async def test_a_container_that_exits_zero_passes(
    checks: CheckService, started: Ticket, root: Path, engine: Path
) -> None:
    write_config(root, container_config(engine))
    row = await checks.run_now(await checks.start(started.id))
    assert (row.verdict, row.exit_code, row.contained.value) == (Verdict.PASSED, 0, "container")


async def test_an_engine_that_is_not_there_runs_nothing_and_says_what_to_do(
    checks: CheckService, started: Ticket, root: Path, tmp_path: Path
) -> None:
    gone = tmp_path / "no-engine"
    write_config(root, container_config(gone))
    _, log = await run(checks, started)
    assert log.read_text() == (
        f"the checks container needs {gone} on PATH; install it, or remove [checks] container "
        "from .code-factory/config.toml\n"
    )


async def test_an_image_is_built_once_from_the_container_file_and_tagged_by_its_digest(
    checks: CheckService, started: Ticket, root: Path, out: Path, engine: Path
) -> None:
    containerfile(root)
    tag = "code-factory-checks:" + hashlib.sha256(b"FROM scratch\n").hexdigest()[:16]
    write_config(
        root,
        container_config(engine, "container_file = '.code-factory/checks.Containerfile'").replace(
            "container = 'img:1'\n", ""
        ),
    )
    _, log = await run(checks, started)
    builds = (out / "build").read_text().splitlines()
    assert builds[0].startswith(f"build --tag {tag} --file ")
    assert builds[0].split()[4].endswith("/.code-factory/checks.Containerfile")
    assert "step 1/1 building" in log.read_text().splitlines()[0]
    assert (out / "run_argv").read_text().splitlines()[-4:-3] == [tag]


async def test_an_image_the_engine_holds_is_not_built_again(
    checks: CheckService, started: Ticket, root: Path, out: Path, engine: Path
) -> None:
    containerfile(root)
    (out / "image_present").write_text("")
    write_config(
        root,
        container_config(engine, "container_file = '.code-factory/checks.Containerfile'").replace(
            "container = 'img:1'\n", ""
        ),
    )
    await run(checks, started)
    assert not (out / "build").exists()


async def test_an_image_the_engine_lost_during_the_wait_is_built_again_before_the_run(
    checks: CheckService, started: Ticket, root: Path, out: Path, engine: Path
) -> None:
    containerfile(root)
    write_config(
        root,
        container_config(engine, "container_file = '.code-factory/checks.Containerfile'").replace(
            "container = 'img:1'\n", ""
        ),
    )
    await run(checks, started)  # the stand-in never holds the image: found missing twice
    assert len((out / "build").read_text().splitlines()) == 2


async def test_an_engine_that_cannot_reach_its_daemon_is_a_container_that_never_started(
    checks: CheckService,
    activity: ActivityService,
    forge: FakeForge,
    started: Ticket,
    root: Path,
    out: Path,
    engine: Path,
) -> None:
    (out / "mode").write_text("daemon")
    write_config(root, container_config(engine))
    check_id, log = await run(checks, started)
    row = await checks.get(check_id)
    assert (row.verdict, row.exit_code) == (Verdict.NO_VERDICT, -1)
    assert "gate: the checks container could not start: no verdict" in log.read_text()
    page = await activity.list_activity(started.id, kinds=["checks"])
    assert page.items[0].data["reason"] == "checks container unavailable"
    assert forge.posts[-1][2:] == (
        "pending",
        "code-factory/checks",
        "The checks container could not start",
    )


async def test_a_daemon_error_after_a_step_started_is_the_commands_own_failure(
    checks: CheckService, started: Ticket, root: Path, out: Path, engine: Path
) -> None:
    (out / "mode").write_text("late")
    write_config(root, container_config(engine))
    check_id, log = await run(checks, started)
    row = await checks.get(check_id)
    assert (row.verdict, row.exit_code) == (Verdict.FAILED, 125)
    assert "could not start" not in log.read_text()


async def test_mounts_are_read_only_and_never_the_state_folder(
    checks: CheckService,
    started: Ticket,
    root: Path,
    out: Path,
    engine: Path,
    tmp_path: Path,
    state: Path,
) -> None:
    packages = tmp_path / "packages"
    packages.mkdir()
    write_config(
        root, container_config(engine, f"container_mounts = ['{packages}:/usr/local/pkgs']")
    )
    await run(checks, started)
    real = str(packages.resolve())
    assert f"{real}:/usr/local/pkgs:ro" in (out / "run_argv").read_text().splitlines()

    state.mkdir(exist_ok=True)
    (out / "run_argv").unlink()
    write_config(root, container_config(engine, f"container_mounts = ['{state}:/s']"))
    check_id, log = await run(checks, started)
    assert "which holds or is in the state folder" in log.read_text()
    assert not (out / "run_argv").exists()
    assert (await checks.get(check_id)).verdict is Verdict.NO_VERDICT


async def test_a_timeout_removes_the_named_container_and_gives_no_verdict(
    checks: CheckService, started: Ticket, root: Path, out: Path, engine: Path
) -> None:
    (out / "mode").write_text("sleep")
    write_config(root, container_config(engine, timeout=1))
    began = time.monotonic()
    check_id, _ = await run(checks, started)
    assert time.monotonic() - began < 20
    row = await checks.get(check_id)
    assert (row.verdict, row.exit_code) == (Verdict.NO_VERDICT, -1)
    assert (out / "rm").read_text().splitlines() == [f"rm -f code-factory-check-{check_id}"]
    assert not reachable(int((out / "pid").read_text()))


async def test_a_cancelled_run_removes_the_container_ends_the_process_and_is_lost(
    checks: CheckService,
    activity: ActivityService,
    started: Ticket,
    root: Path,
    out: Path,
    engine: Path,
) -> None:
    (out / "mode").write_text("sleep")
    write_config(root, container_config(engine))
    check_id = await checks.start(started.id)
    task = asyncio.create_task(checks.run_now(check_id))
    for _ in range(300):
        if (out / "pid").exists():
            break
        await asyncio.sleep(0.05)
    pid = int((out / "pid").read_text())
    assert reachable(pid)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    row = await checks.get(check_id)
    assert row.state is RunState.LOST
    assert row.verdict is None
    assert (out / "rm").read_text().splitlines() == [f"rm -f code-factory-check-{check_id}"]
    assert not reachable(pid)
    assert (await activity.list_activity(started.id, kinds=["checks"])).items == []
    assert (await checks.latest(started.id)).state is ViewState.NO_VERDICT


@pytest.mark.parametrize(
    ("entry", "sentence"),
    [
        ("~/.ssh:/s", "the host folder is, holds or is in the home folder or a secret folder"),
        ("~:/x", "expected <host folder>:<folder inside>"),
        ("/:/x", "expected <host folder>:<folder inside>"),
        ("/a/../b:/c", "expected <host folder>:<folder inside>"),
        ("a:b:c", "expected <host folder>:<folder inside>"),
    ],
)
async def test_a_mount_that_reaches_a_secret_or_is_malformed_is_refused_before_the_engine_runs(
    entry: str,
    sentence: str,
    uow: UnitOfWork,
    git_service: GitService,
    root: Path,
    state: Path,
    out: Path,
    engine: Path,
    sandbox: FakeSandbox,
    tmp_path: Path,
) -> None:
    logs = LogFiles(state)
    containers = ContainerChecks(
        agents=AgentService(uow),
        git=git_service,
        logs=logs,
        places=lambda: [root, tmp_path],
        state_dir=state,
        denials=sandbox,
    )
    log = state / "checks" / "x.log"
    spec = ContainerSpec(engine=str(engine), image="img:1", mounts=(entry,))
    ctx = ContainerRun(REPO, root, spec, 1, "true", root, log, 30.0, root / ".git")

    class Free:
        async def __aenter__(self) -> None: ...
        async def __aexit__(self, *_: object) -> None: ...

    assert await containers.run(ctx, Free) == -1
    assert sentence in log.read_text()
    assert not (out / "run_argv").exists()


async def test_a_container_check_killed_once_takes_its_turn_again_and_passes(
    checks: CheckService, started: Ticket, root: Path, out: Path, engine: Path
) -> None:
    write_config(root, container_config(engine))
    (out / "mode").write_text("killonce")
    check_id = await checks.start(started.id)
    row = await asyncio.wait_for(checks.run_now(check_id), timeout=20)
    assert (row.state, row.verdict) == (RunState.FINISHED, Verdict.PASSED)


class Free:
    async def __aenter__(self) -> None: ...
    async def __aexit__(self, *_: object) -> None: ...


async def test_the_git_mounts_come_from_the_git_folder_read_before_setup_not_the_trees_file(
    uow: UnitOfWork,
    git_service: GitService,
    root: Path,
    state: Path,
    out: Path,
    engine: Path,
    sandbox: FakeSandbox,
    tmp_path: Path,
) -> None:
    common = tmp_path / "common"
    admin = common / "worktrees" / "t"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n")
    secret = tmp_path / "secret"
    forged = tmp_path / "tree" / "fake"
    forged.mkdir(parents=True)
    (forged / "commondir").write_text(f"{secret}\n")
    (tmp_path / "tree" / ".git").write_text(f"gitdir: {forged}\n")
    containers = ContainerChecks(
        agents=AgentService(uow),
        git=git_service,
        logs=LogFiles(state),
        places=lambda: [root, tmp_path],
        state_dir=state,
        denials=sandbox,
    )
    spec = ContainerSpec(engine=str(engine), image="img:1")
    log = state / "checks" / "x.log"
    ctx = ContainerRun(REPO, root, spec, 1, "true", tmp_path / "tree", log, 30.0, admin)
    secret.mkdir()
    assert await containers.run(ctx, Free) == 0
    argv = (out / "run_argv").read_text().splitlines()
    read_only = {a for a in argv if a.endswith(":ro")}
    real_common, real_admin = str(common.resolve()), str(admin.resolve())
    assert read_only == {f"{real_common}:{real_common}:ro", f"{real_admin}:{real_admin}:ro"}
