"""Run the lifecycle acceptance cases on the working tree and optionally on a Git revision."""

import argparse
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from gate_delta import git

from code_factory.platform.config import DATABASE_URL_VARIABLE, load_settings, parse_database_url

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "tests/runs/test_run_lifecycle_replay.py"
LIVE = ROOT / "tests/runs/live_run_lifecycle.py"
CASE_COUNT = 4
TIMEOUT = 60
MAX_REPORT_BYTES = 1_000_000


def test_env() -> dict[str, str]:
    """Use the configured test database or the standard local test database."""
    env = {key: val for key, val in os.environ.items() if not key.startswith("PYTEST_")}
    if DATABASE_URL_VARIABLE not in env:
        url = parse_database_url(load_settings().database_url.get_secret_value())
        if url.host not in {"localhost", "127.0.0.1", "::1"} or url.query:
            msg = f"set {DATABASE_URL_VARIABLE} to a local test database URL"
            raise ValueError(msg)
        env[DATABASE_URL_VARIABLE] = url.set(database="code_factory_test").render_as_string(
            hide_password=False
        )
    return env


def replay(source: Path, label: str, directory: Path, env: dict[str, str]) -> bool:
    """Use the same test code against one source tree, with its own test schema."""
    print(f"Lifecycle replay on {label}", flush=True)
    report = directory / "replay.xml"
    report.unlink(missing_ok=True)
    result = subprocess.run(  # noqa: S603  # fixed suite and arguments, no shell
        [
            sys.executable, "-m", "pytest", "-q", "-n", "1", "-o", "addopts=",
            "--tb=short", "--show-capture=no", f"--junitxml={report}", str(SUITE),
        ],
        cwd=source,
        env={**env, "PYTHONPATH": str(source / "src")},
        check=False,
        timeout=TIMEOUT,
    )  # fmt: skip
    if not report.is_file() or report.stat().st_size > MAX_REPORT_BYTES:
        msg = f"{label} did not produce a complete replay report"
        raise ValueError(msg)
    cases = ET.parse(report).findall(".//testcase")  # noqa: S314  # bounded local pytest report
    if len(cases) != CASE_COUNT or any(
        case.find("error") is not None or case.find("skipped") is not None for case in cases
    ):
        msg = f"{label} did not execute all {CASE_COUNT} replay scenarios"
        raise ValueError(msg)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        failures = [failure for case in cases if (failure := case.find("failure")) is not None]
        if failures and all(
            failure.get("message", "").startswith("AssertionError: ")
            and " > " in failure.get("message", "").splitlines()[0]
            for failure in failures
        ):
            return False
    msg = f"{label} replay did not finish with a checkpoint verdict"
    raise ValueError(msg)


def main() -> int:
    """A comparison reports base mismatches and requires all candidate cases to pass."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="run the exact same suite on this Git revision first")
    parser.add_argument(
        "--live", action="store_true", help="also run the installed Claude and Codex CLIs"
    )
    args = parser.parse_args()
    os.chdir(ROOT)
    try:
        env = test_env()
        with tempfile.TemporaryDirectory(prefix="code-factory-replay-") as temporary:
            directory = Path(temporary)
            if args.base:
                ref = git("rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}")
                commit = ref.stdout.decode().strip()
                source = directory / "base"
                archive = git("archive", commit, "src", "alembic", "alembic.ini")
                with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
                    tar.extractall(source, filter="data")
                replay(source, f"base {commit[:12]}", directory, env)
            if not replay(ROOT, "working tree", directory, env):
                return 1
            if args.live:
                return subprocess.run(  # noqa: S603  # fixed suite, no shell
                    [sys.executable, "-m", "pytest", "-q", "-n", "1", "-o", "addopts=", str(LIVE)],
                    cwd=ROOT,
                    env={**env, "PYTHONPATH": str(ROOT / "src")},
                    check=False,
                    timeout=260,
                ).returncode
            return 0
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        tarfile.TarError,
        ET.ParseError,
    ) as error:
        parser.exit(2, f"Lifecycle replay could not finish: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
