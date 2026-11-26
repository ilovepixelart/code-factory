"""Install a wheel outside the checkout, then smoke-test it and restore its test schema."""

import argparse
import http.cookiejar
import json
import os
import re
import selectors
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import HTTPCookieProcessor, build_opener

from sqlalchemy.engine import URL, make_url

from code_factory.sample.rules import check_target

ROOT = Path(__file__).resolve().parents[1]
PORT_LINE = re.compile(rb"serving on (http://127\.0\.0\.1:\d+)")
ASSET = re.compile(rb'(?:src|href)="(/assets/[^"]+)"')


def _run(argv: list[str], work: Path, env: dict[str, str]) -> None:
    subprocess.run(argv, cwd=work, env=env, check=True, timeout=180)  # noqa: S603


def _install(wheel: Path, work: Path, env: dict[str, str]) -> str:
    constraints = work / "constraints.txt"
    _run(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--output-file",
            str(constraints),
        ],
        ROOT,
        env,
    )
    bin_dir = work / "venv" / "bin"
    _run(["uv", "venv", "--python", sys.executable, str(bin_dir.parent)], work, env)
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(bin_dir / "python"),
            "--strict",
            "--constraint",
            str(constraints),
            str(wheel),
        ],
        work,
        env,
    )
    return str(bin_dir / "code-factory")


def _board_line(server: subprocess.Popen[bytes]) -> bytes:
    if server.stdout is None:
        msg = "the installed server has no stdout"
        raise RuntimeError(msg)
    with selectors.DefaultSelector() as selector:
        selector.register(server.stdout, selectors.EVENT_READ)
        if selector.select(30):
            return server.stdout.readline().strip()
    msg = "the installed server did not announce its address in 30 seconds"
    raise RuntimeError(msg)


def _verify_board(binary: str, work: Path, env: dict[str, str]) -> None:
    with subprocess.Popen(  # noqa: S603  # the installed CLI, with fixed arguments
        [binary, "serve", "--no-open"], cwd=work, env=env, stdout=subprocess.PIPE, bufsize=0
    ) as server:
        try:
            started = PORT_LINE.fullmatch(_board_line(server))
            sign_in = _board_line(server).removeprefix(b"sign in: ")
            if started is None or not sign_in.startswith(started[1] + b"/owner/"):
                msg = "the installed server did not announce a local address and sign-in link"
                raise RuntimeError(msg)
            base = started[1].decode()
            opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            with opener.open(sign_in.decode(), timeout=10) as response:
                page = response.read()
            assets = ASSET.findall(page)
            if b'<div id="app">' not in page or not assets:
                msg = "the installed server did not serve the Vue build"
                raise RuntimeError(msg)
            for asset in assets:
                with opener.open(base + asset.decode(), timeout=10) as response:
                    response.read()
            with opener.open(base + "/api/ready", timeout=10) as response:
                if json.load(response) != {"status": "ready"}:
                    msg = "the installed server is not ready"
                    raise RuntimeError(msg)
            with opener.open(base + "/api/tickets/sample/CF-1", timeout=10) as response:
                if b"Specs written" not in response.read():
                    msg = "the signed-in board did not return the seeded ticket"
                    raise RuntimeError(msg)
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()


def _smoke(wheel: Path, work: Path, url: str) -> None:
    connection = make_url(url)
    schema = f"release_{work.name.rsplit('-', 1)[-1]}"
    check_target(connection.host, connection.database, dict(connection.query), schema)
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "VIRTUAL_ENV"}}
    env.update(
        CODE_FACTORY_DATABASE_URL=url,
        CODE_FACTORY_DB_SCHEMA=schema,
        CODE_FACTORY_HOST="127.0.0.1",
        CODE_FACTORY_PORT="0",
        CODE_FACTORY_STATE_DIR=str(work / "state"),
        CODE_FACTORY_RUN_DIR=str(work / "run"),
        CODE_FACTORY_RELEASES_DIR=str(work / "releases"),
    )
    binary = _install(wheel, work, env)
    database = URL.create(
        "postgresql",
        username=connection.username,
        host=connection.host,
        port=connection.port,
        database=connection.database,
    )
    pg_env = {**env, "PGPASSWORD": connection.password or ""}
    dsn = database.render_as_string(hide_password=False)
    backup = str(work / "schema.dump")
    _run([binary, "sample-prepare"], work, env)
    try:
        _run([binary, "db", "upgrade"], work, env)
        _run([binary, "sample-load", "board"], work, env)
        _verify_board(binary, work, env)
        _run(
            ["pg_dump", "--format=custom", f"--schema={schema}", "--file", backup, dsn],
            work,
            pg_env,
        )
        _run([binary, "sample-drop"], work, env)
        _run(["pg_restore", "--exit-on-error", "--dbname", dsn, backup], work, pg_env)
        _run([binary, "db", "check"], work, env)
        _verify_board(binary, work, env)
    finally:
        _run([binary, "sample-drop"], work, env)


def main() -> int:
    """Check an isolated wheel with the runner's explicitly selected local test database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    url = os.environ.get("CODE_FACTORY_GATE_DATABASE_URL")
    if url is None or url == "":
        parser.error("set CODE_FACTORY_GATE_DATABASE_URL to a local _test database")
    with tempfile.TemporaryDirectory(prefix="code-factory-release-") as directory:
        _smoke(args.wheel.resolve(strict=True), Path(directory), url)
    print("The installed wheel migrated, served the signed-in app and restored a backup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
