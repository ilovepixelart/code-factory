"""Smoke-test the Compose setup with a disposable project and persisted volumes."""

import http.cookiejar
import os
import re
import socket
import subprocess
import time
import uuid
from pathlib import Path
from urllib.request import HTTPCookieProcessor, build_opener

ROOT = Path(__file__).resolve().parents[1]


def _run(env: dict[str, str], *argv: str) -> str:
    result = subprocess.run(  # noqa: S603  # fixed Compose commands and an isolated project
        argv, cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=300
    )
    if result.returncode:
        msg = f"{' '.join(argv)} failed: {result.stderr.strip()}"
        raise RuntimeError(msg)
    return result.stdout


def main() -> int:
    """Start and recreate the stack and check that the owner session survives."""
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "COMPOSE_PROJECT_NAME": f"code-factory-smoke-{uuid.uuid4().hex[:12]}",
        "CODE_FACTORY_COMPOSE_PORT": str(port),
    }
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        began = time.monotonic()
        output = _run(env, "sh", "scripts/compose.sh")
        first_s = time.monotonic() - began
        link = re.search(rf"{re.escape(base)}/owner/[^\s]+", output)
        if link is None:
            msg = "the setup command did not print a sign-in link on the Compose port"
            raise RuntimeError(msg)
        with opener.open(link[0], timeout=10) as response:
            if b'<div id="app">' not in response.read():
                msg = "Compose did not serve the signed-in Vue application"
                raise RuntimeError(msg)
        execute = ("docker", "compose", "exec", "-T", "factory")
        _run(env, *execute, "git", "init", "--initial-branch=main", "/repositories/example")
        _run(env, *execute, "code-factory-container", "track", "/repositories/example")
        _run(env, "docker", "compose", "down")
        began = time.monotonic()
        _run(env, "sh", "scripts/compose.sh")
        restart_s = time.monotonic() - began
        with opener.open(base + "/api/repositories", timeout=10) as response:
            if b'"example"' not in response.read():
                msg = "Compose did not preserve the signed-in owner's repository after recreation"
                raise RuntimeError(msg)
    finally:
        _run(env, "docker", "compose", "down", "--volumes")
    print(
        "Compose sign-in and persistence passed. "
        f"First start {first_s:.1f}s, restart {restart_s:.1f}s."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
