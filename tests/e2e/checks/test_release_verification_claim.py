"""A serving Factory and an explicit verification share one PostgreSQL claim."""

import asyncio
import socket
import sys
from pathlib import Path

from code_factory.app import build_resources, build_services
from code_factory.checks.service import CheckService
from code_factory.platform.config import Settings
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from git_support import git, make_repo

CLI = str(Path(sys.executable).parent / "code-factory")
REPOSITORY = "sample"
VERSION = "0.1.0"


async def appeared(path: Path) -> None:
    async with asyncio.timeout(12):
        while not path.is_file():  # noqa: ASYNC110  # a subprocess writes the sentinel
            await asyncio.sleep(0.05)


async def verify(env: dict[str, str]) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        CLI,
        "checks",
        "verify",
        REPOSITORY,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode is not None
    return process.returncode, stdout.decode()


async def test_manual_verification_cannot_overlap_a_server_and_recovers_after_its_crash(
    serve_env: dict[str, str], tmp_path: Path
) -> None:
    root = make_repo(tmp_path)
    config = root / ".code-factory" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        "[release]\nverify = 'echo started >> attempts; "
        "if mkdir first 2>/dev/null; then touch running; "
        "while [ ! -f proceed ]; do sleep 0.05; done; touch finished; fi'\n"
    )
    state = tmp_path / "state"
    settings = Settings(db_schema=serve_env["CODE_FACTORY_DB_SCHEMA"], state_dir=state)
    resources = build_resources(settings)
    services = build_services(resources)
    env = {
        **serve_env,
        "CODE_FACTORY_STATE_DIR": str(state),
        "CODE_FACTORY_DB_POOL_SIZE": "1",
        "CODE_FACTORY_DB_MAX_OVERFLOW": "0",
    }
    with socket.socket() as port:
        port.bind(("127.0.0.1", 0))
        address = str(port.getsockname()[1])
    await services.get(RepositoryService).track(root)
    releases = services.get(ReleaseService)
    await releases.draft(REPOSITORY, VERSION, by="alex")
    await releases.publish(REPOSITORY, VERSION, by="alex")
    await releases.record_tag_commit(
        REPOSITORY, VERSION, git(root, "rev-parse", "main").strip(), by="alex"
    )
    await releases.record_tagged(REPOSITORY, VERSION, by="alex")
    log = tmp_path / "server.log"
    with log.open("wb") as output_stream:
        server = await asyncio.create_subprocess_exec(
            CLI,
            "serve",
            env={**env, "CODE_FACTORY_PORT": address, "CODE_FACTORY_DB_POOL_SIZE": "10"},
            stdout=asyncio.subprocess.DEVNULL,
            stderr=output_stream,
        )
    try:
        await appeared(root / "running")
        status, output = await verify(env)
        assert status == 1, output
        assert "verification of sample is running already" in output
        assert (root / "attempts").read_text().splitlines() == ["started"]
        server.kill()
        await server.wait()
        (root / "proceed").touch()
        await appeared(root / "finished")

        status, output = await verify(env)
        assert status == 0, output
        assert (root / "attempts").read_text().splitlines() == ["started", "started"]
        results = await services.get(CheckService).verify_records(REPOSITORY)
        assert [(row.release, row.exit_code) for row in results] == [(VERSION, 0)]
    except TimeoutError as error:
        error.add_note(log.read_text()[-6000:])
        raise
    finally:
        (root / "proceed").touch()
        if server.returncode is None:
            server.kill()
            await server.wait()
        await resources.engine.dispose()
