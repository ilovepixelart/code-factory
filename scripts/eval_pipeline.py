"""Evaluate variations of the agent pipeline in disposable checkouts of one commit."""

import argparse
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import time
import tomllib
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as wall_time
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from gate_delta import git

FLAGS = {"spec-reader": "spec_reader", "plan-critic": "plan_critic", "review": "review"}
ROLES = ("qa", "security", "tests")
TIMEOUT = 600
MAX_SETUPS = 12
TRIAL_CAPS = (2, 3)
MAX_CASES = 128
MAX_COST_CENTS = (2**53 - 1) // (MAX_CASES * 2)
MAX_OUTCOME_BYTES = 256 * 1024
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
STATES = ("merged", "closed", "open")


@dataclass(frozen=True)
class Setup:
    """One set of repository settings for the evaluation."""

    name: str
    steps: dict[str, bool]
    fix_rounds: int | None = None


class Outcome(TypedDict):
    """The owner's driver measurements for one case by the observation deadline."""

    case_id: str
    state: str
    fix_rounds: int
    agent_cost_cents: int | None
    owner_cost_cents: int | None


class Run(TypedDict):
    """What happened when one setup ran."""

    name: str
    head: str
    steps: dict[str, bool]
    exit_code: int | None
    seconds: float
    fix_rounds: NotRequired[int]
    outcomes: NotRequired[list[Outcome]]
    outcomes_error: NotRequired[str]


def _trial_cases(value: object, profiles: list[Setup]) -> list[str]:
    if not isinstance(value, dict) or value.keys() != {"cases"}:
        msg = "give the fix-round trial a cases list"
        raise ValueError(msg)
    cases = value["cases"]
    if (
        not isinstance(cases, list)
        or not 1 <= len(cases) <= MAX_CASES
        or any(not isinstance(case, str) or not CASE_ID.fullmatch(case) for case in cases)
        or len(cases) != len(set(cases))
    ):
        msg = "give the fix-round trial one to 128 unique case IDs"
        raise ValueError(msg)
    if (
        len(profiles) != len(TRIAL_CAPS)
        or {profile.fix_rounds for profile in profiles} != set(TRIAL_CAPS)
        or profiles[0].steps != profiles[1].steps
    ):
        msg = "the fix-round trial needs caps 2 and 3 with identical step settings"
        raise ValueError(msg)
    return cast("list[str]", cases)


def setups(path: Path) -> tuple[list[Setup], list[str]]:
    """Read the pipeline variants and the common case IDs of an optional trial."""
    manifest = tomllib.loads(path.read_text(encoding="utf-8"))
    items = manifest.get("setup")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_SETUPS:
        msg = "name one to twelve [[setup]] entries"
        raise ValueError(msg)
    result = []
    seen = set()
    for entry in items:
        name = entry["name"]
        steps = entry.get("steps", {})
        fix_rounds = entry.get("fix_rounds")
        if not isinstance(name, str) or not name.strip() or name in seen:
            msg = "each setup needs a unique, nonempty name"
            raise ValueError(msg)
        if not isinstance(steps, dict) or any(
            key not in (*FLAGS, *ROLES) or not isinstance(value, bool)
            for key, value in steps.items()
        ):
            msg = "set each named step to true or false"
            raise ValueError(msg)
        if fix_rounds is not None and (
            isinstance(fix_rounds, bool) or not isinstance(fix_rounds, int) or fix_rounds < 1
        ):
            msg = "fix_rounds needs a positive integer"
            raise ValueError(msg)
        seen.add(name)
        result.append(Setup(name, steps, fix_rounds))
    trial = manifest.get("fix_round_trial")
    return result, [] if trial is None else _trial_cases(trial, result)


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


def configure(checkout: Path, profile: Setup) -> None:
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
    for step, enabled in profile.steps.items():
        if step in FLAGS:
            agents[FLAGS[step]] = enabled
        elif enabled and step not in roles:
            roles.append(step)
        elif not enabled:
            roles = [role for role in roles if role != step]
    agents.update(review_roles=roles, ship=False, merge_approval=True)
    if profile.fix_rounds is not None:
        agents["fix_rounds"] = profile.fix_rounds
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


def outcomes(path: Path, cases: list[str], cap: int) -> list[Outcome]:
    """Read a bounded response with exactly the requested cases and trusted column types."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            msg = "the driver outcome report must be a regular file"
            raise ValueError(msg)
        data = file.read(MAX_OUTCOME_BYTES + 1)
    if len(data) > MAX_OUTCOME_BYTES:
        msg = "the driver outcome report exceeds 256 KiB"
        raise ValueError(msg)
    rows = json.loads(data)
    count_error = "the driver did not return exactly one outcome per named case"
    if not isinstance(rows, list) or len(rows) != len(cases):
        raise ValueError(count_error)
    measured: dict[str, Outcome] = {}
    for row in rows:
        if not isinstance(row, dict) or row.keys() != Outcome.__required_keys__:
            msg = "each outcome must have case_id, state, fix_rounds and both cost fields"
            raise ValueError(msg)
        case = row["case_id"]
        if not isinstance(case, str) or case not in cases or case in measured:
            raise ValueError(count_error)
        if row["state"] not in STATES:
            msg = f"case {case!r} has an invalid delivery state"
            raise ValueError(msg)
        rounds = row["fix_rounds"]
        if not _whole(rounds, cap):
            msg = f"case {case!r} has an invalid fix-round count for cap {cap}"
            raise ValueError(msg)
        for field in ("agent_cost_cents", "owner_cost_cents"):
            cost = row[field]
            if cost is not None and not _whole(cost, MAX_COST_CENTS):
                msg = f"case {case!r} has invalid {field}"
                raise ValueError(msg)
        measured[case] = cast("Outcome", row)
    return [measured[case] for case in cases]


def _whole(value: object, limit: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= limit


def _outcome_cost(outcome: Outcome) -> int | None:
    agent, owner = outcome["agent_cost_cents"], outcome["owner_cost_cents"]
    return None if agent is None or owner is None else agent + owner


def comparison(runs: list[Run]) -> dict[str, object] | None:
    """Compare the matched outcomes when both trial arms finished reliably."""
    results = {run["fix_rounds"]: run["outcomes"] for run in runs if "outcomes" in run}
    if results.keys() != set(TRIAL_CAPS):
        return None
    merges: dict[str, list[str]] = {"both": [], "two_only": [], "three_only": [], "neither": []}
    buckets = {
        (True, True): "both",
        (True, False): "two_only",
        (False, True): "three_only",
        (False, False): "neither",
    }
    paired_cases = []
    delta = 0
    for two, three in zip(results[2], results[3], strict=True):
        case = two["case_id"]
        merges[buckets[two["state"] == "merged", three["state"] == "merged"]].append(case)
        two_cost, three_cost = _outcome_cost(two), _outcome_cost(three)
        if two_cost is not None and three_cost is not None:
            paired_cases.append(case)
            delta += three_cost - two_cost
    return {
        "arms": [
            {
                "fix_rounds": cap,
                **{state: sum(row["state"] == state for row in results[cap]) for state in STATES},
                "rounds_used": sum(row["fix_rounds"] for row in results[cap]),
            }
            for cap in TRIAL_CAPS
        ],
        "merges": merges,
        "cost": {
            "paired_cases": paired_cases,
            "three_minus_two_cents": delta if paired_cases else None,
        },
    }


def evaluate(root: Path, profiles: list[Setup], command: list[str], cases: list[str]) -> list[Run]:
    """Run an owner-supplied driver for each setup at the same Git commit."""
    head = git("rev-parse", "--verify", "HEAD").stdout.decode().strip()
    reports = []
    with tempfile.TemporaryDirectory(prefix="code-factory-pipeline-eval-") as scratch:
        for index, profile in enumerate(profiles):
            checkout = Path(scratch).resolve() / f"setup-{index}"
            git("clone", "--quiet", "--shared", "--no-checkout", "--", str(root), str(checkout))
            git("-C", str(checkout), "remote", "remove", "origin")
            git("-C", str(checkout), "checkout", "--quiet", "--detach", head)
            configure(checkout, profile)
            start = time.monotonic()
            env = dict(
                os.environ, CODE_FACTORY_EVAL_SETUP=profile.name, CODE_FACTORY_EVAL_HEAD=head
            )
            response = Path(scratch).resolve() / f"outcomes-{index}.json"
            if cases:
                env.update(
                    CODE_FACTORY_EVAL_CASES=json.dumps(cases),
                    CODE_FACTORY_EVAL_OUTCOMES=str(response),
                )
            code = run_driver(command, checkout, env)
            report = Run(
                name=profile.name,
                head=head,
                steps=profile.steps,
                exit_code=code,
                seconds=round(time.monotonic() - start, 3),
            )
            if profile.fix_rounds is not None:
                report["fix_rounds"] = profile.fix_rounds
                if cases and code == 0:
                    try:
                        report["outcomes"] = outcomes(response, cases, profile.fix_rounds)
                    except (OSError, ValueError) as error:
                        report["outcomes_error"] = str(error)
            reports.append(report)
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
        profiles, cases = setups(args.manifest)
        runs = evaluate(root, profiles, args.command, cases)
        with report.open("x", encoding="utf-8") as output:
            result = (
                {"cases": cases, "runs": runs, "comparison": comparison(runs)} if cases else runs
            )
            json.dump(result, output, indent=2)
            output.write("\n")
        return int(any(run["exit_code"] != 0 or "outcomes_error" in run for run in runs))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"The pipeline evaluation could not run: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
