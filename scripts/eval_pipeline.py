"""Evaluate variations of the agent pipeline in disposable checkouts of one commit."""

import argparse
import json
import os
import signal
import subprocess
import tempfile
import time
import tomllib
from contextlib import suppress
from datetime import date, datetime
from datetime import time as wall_time
from pathlib import Path

from gate_delta import git

FLAGS = {"spec-reader": "spec_reader", "plan-critic": "plan_critic", "review": "review"}
ROLES = ("qa", "security", "tests")
TIMEOUT = 600
MAX_SETUPS = 12


def setups(path: Path) -> list[tuple[str, dict[str, bool]]]:
    """Read a bounded group of uniquely named pipeline variants."""
    items = tomllib.loads(path.read_text(encoding="utf-8")).get("setup")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_SETUPS:
        msg = "name one to twelve [[setup]] entries"
        raise ValueError(msg)
    result = []
    seen = set()
    for entry in items:
        name = entry["name"]
        steps = entry.get("steps", {})
        if not isinstance(name, str) or not name.strip() or name in seen:
            msg = "each setup needs a unique, nonempty name"
            raise ValueError(msg)
        if not isinstance(steps, dict) or any(
            key not in (*FLAGS, *ROLES) or not isinstance(value, bool)
            for key, value in steps.items()
        ):
            msg = "set each named step to true or false"
            raise ValueError(msg)
        seen.add(name)
        result.append((name, steps))
    return result


def toml(value: object) -> str:
    """Serialize parsed TOML as scalars, arrays, and inline tables."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime, date, wall_time)):
        return value.isoformat()
    if isinstance(value, list):
        return f"[{', '.join(toml(item) for item in value)}]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{toml(key)} = {toml(item)}" for key, item in value.items()) + "}"
    msg = "the existing repository settings contain an unsupported TOML value"
    raise ValueError(msg)


def configure(checkout: Path, steps: dict[str, bool]) -> None:
    """Apply the variant to the settings the board reads in this checkout."""
    path = checkout / ".code-factory" / "config.toml"
    if path.resolve() != path:
        msg = "the eval checkout's configuration is linked"
        raise ValueError(msg)
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    agents = data.setdefault("agents", {})
    roles = agents.get("review_roles", [])
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        msg = "the checkout's review_roles must be a list of names"
        raise ValueError(msg)
    for step, enabled in steps.items():
        if step in FLAGS:
            agents[FLAGS[step]] = enabled
        elif enabled and step not in roles:
            roles.append(step)
        elif not enabled:
            roles = [role for role in roles if role != step]
    agents.update(review_roles=roles, ship=False, merge_approval=True)
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "".join(f"{toml(key)} = {toml(value)}\n" for key, value in data.items()),
        encoding="utf-8",
    )


def run_driver(command: list[str], checkout: Path, env: dict[str, str]) -> int | None:
    """Bound the owner driver and stop its process group on exit."""
    with subprocess.Popen(  # noqa: S603  # the owner supplied this driver as argv
        command, cwd=checkout, env=env, start_new_session=True
    ) as child:
        try:
            return child.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return None
        finally:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)


def evaluate(
    root: Path, profiles: list[tuple[str, dict[str, bool]]], command: list[str]
) -> list[dict[str, object]]:
    """Run an owner-supplied driver for each setup at the same Git commit."""
    head = git("rev-parse", "--verify", "HEAD").stdout.decode().strip()
    reports = []
    with tempfile.TemporaryDirectory(prefix="code-factory-pipeline-eval-") as scratch:
        for index, (name, steps) in enumerate(profiles):
            checkout = Path(scratch).resolve() / f"setup-{index}"
            git("clone", "--quiet", "--shared", "--no-checkout", "--", str(root), str(checkout))
            git("-C", str(checkout), "remote", "remove", "origin")
            git("-C", str(checkout), "checkout", "--quiet", "--detach", head)
            configure(checkout, steps)
            start = time.monotonic()
            env = dict(os.environ, CODE_FACTORY_EVAL_SETUP=name, CODE_FACTORY_EVAL_HEAD=head)
            code = run_driver(command, checkout, env)
            reports.append(
                {
                    "name": name,
                    "head": head,
                    "steps": steps,
                    "exit_code": code,
                    "seconds": round(time.monotonic() - start, 3),
                }
            )
    return reports


def main() -> int:
    """Write the reproducible setup results to a new output file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER, metavar="DRIVER")
    args = parser.parse_args()
    if not args.command:
        parser.error("supply a driver executable and its arguments")
    try:
        root = Path(git("rev-parse", "--show-toplevel").stdout.decode().strip()).resolve()
        report = args.report.resolve()
        if report.is_relative_to(root) or report.exists() or args.report.is_symlink():
            parser.error("use a new report path outside the repository")
        profiles = setups(args.manifest)
        runs = evaluate(root, profiles, args.command)
        with report.open("x", encoding="utf-8") as output:
            json.dump(runs, output, indent=2)
            output.write("\n")
        return int(any(run["exit_code"] != 0 for run in runs))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"The pipeline evaluation could not run: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
