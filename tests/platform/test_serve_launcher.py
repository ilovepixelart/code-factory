"""`serve` as the browser tests launch it: a free port, its address printed, stopped by stdin."""

import re
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

COMMAND = str(Path(sys.executable).parent / "code-factory")


def _launch(env: dict[str, str], extra_env: dict[str, str]) -> subprocess.Popen[str]:
    env = {**env, "CODE_FACTORY_PORT": "0", **extra_env}
    return subprocess.Popen(  # noqa: S603  # our own console script, no shell
        [COMMAND, "serve"],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _end(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    process.wait()
    for stream in (process.stdin, process.stdout):
        if stream is not None:
            stream.close()


def test_port_zero_serves_on_a_free_port_it_prints_and_stops_when_stdin_closes(
    serve_env: dict[str, str],
) -> None:
    process = _launch(serve_env, {"CODE_FACTORY_STOP_AT_EOF": "1"})
    try:
        assert process.stdout is not None
        first = process.stdout.readline().strip()
        found = re.fullmatch(r"serving on http://127\.0\.0\.1:(\d+)", first)
        assert found is not None, first
        port = int(found.group(1))
        assert port != 0
        link = re.fullmatch(
            rf"sign in: (http://127\.0\.0\.1:{port}/owner/cfn_[A-Za-z0-9_-]{{43}})",
            process.stdout.readline().strip(),
        )
        assert link is not None
        signed = httpx.get(link.group(1), timeout=5)
        assert signed.status_code == 303
        assert "code_factory_owner=cfs_" in signed.headers["set-cookie"]
        assert httpx.get(f"http://127.0.0.1:{port}/api/ready", timeout=5).status_code == 200

        assert process.stdin is not None
        process.stdin.close()

        assert process.wait(timeout=15) == 0
    finally:
        _end(process)


def test_without_the_stop_variable_a_closed_stdin_does_not_stop_the_server(
    serve_env: dict[str, str],
) -> None:
    process = _launch(serve_env, {})
    try:
        assert process.stdout is not None
        found = re.fullmatch(
            r"serving on http://127\.0\.0\.1:(\d+)", process.stdout.readline().strip()
        )
        assert found is not None
        assert process.stdin is not None
        process.stdin.close()
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=2)
        assert (
            httpx.get(f"http://127.0.0.1:{found.group(1)}/api/ready", timeout=5).status_code == 200
        )
    finally:
        _end(process)


def test_an_occupied_port_exits_with_a_retry_command(serve_env: dict[str, str]) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        result = subprocess.run(  # noqa: S603  # our own console script, no shell
            [COMMAND, "serve"],
            env={**serve_env, "CODE_FACTORY_HOST": "127.0.0.1", "CODE_FACTORY_PORT": str(port)},
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == (
        f"code-factory: http://127.0.0.1:{port} is already in use. "
        "If Factory is already running, open that board. "
        "To start on a free port, rerun with CODE_FACTORY_PORT=0."
    )


def _has_ipv6_loopback() -> bool:
    try:
        with socket.socket(socket.AF_INET6) as probe:
            probe.bind(("::1", 0))
    except OSError:
        return False
    return True


@pytest.mark.skipif(not _has_ipv6_loopback(), reason="no IPv6 loopback on this machine")
def test_an_ipv6_loopback_host_is_bound_and_printed_in_brackets(serve_env: dict[str, str]) -> None:
    process = _launch(serve_env, {"CODE_FACTORY_HOST": "::1", "CODE_FACTORY_STOP_AT_EOF": "1"})
    try:
        assert process.stdout is not None
        found = re.fullmatch(
            r"serving on (http://\[::1\]:(\d+))", process.stdout.readline().strip()
        )
        assert found is not None
        link = process.stdout.readline().strip()
        assert re.fullmatch(
            rf"sign in: http://\[::1\]:{found.group(2)}/owner/cfn_[A-Za-z0-9_-]{{43}}", link
        )
        assert httpx.get(f"{found.group(1)}/api/ready", timeout=5).status_code == 200
    finally:
        _end(process)
