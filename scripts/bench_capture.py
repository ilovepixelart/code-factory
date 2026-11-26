"""Time the capture hook: p50 and p99 of one run, idle and with eight running at once.

The hook runs at least twice per tool call and an interpreter start is its floor, so this is the
number that decides whether it may be installed as a command the agent waits for. Run it on a
quiet machine: `uv run python scripts/bench_capture.py [--runs 1000]`. It writes into a temporary
state folder and prints one line per scenario, in milliseconds.
"""

import argparse
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "src/code_factory/sessions/rules/capture.py"
PAYLOAD = (
    b'{"session_id": "bench", "hook_event_name": "PreToolUse", "tool_name": "Bash", '
    b'"tool_use_id": "t1", "tool_input": {"command": "uv run pytest", "description": "tests"}}'
)
PARALLEL = 8


def run_once(state: str) -> float:
    """Milliseconds one hook run takes, from start to exit."""
    started = time.perf_counter()
    subprocess.run(  # noqa: S603  # our own interpreter on our own file
        [sys.executable, "-I", "-S", str(HOOK)],
        input=PAYLOAD,
        env={"CODE_FACTORY_STATE_DIR": state},
        check=True,
        capture_output=True,
    )
    return (time.perf_counter() - started) * 1000


def percentile(values: list[float], share: float) -> float:
    """The value `share` of the way up the sorted list."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * share))]


def report(name: str, values: list[float]) -> None:
    """Print one scenario."""
    print(
        f"{name}: p50 {statistics.median(values):.1f} ms, p99 {percentile(values, 0.99):.1f} ms, "
        f"min {min(values):.1f} ms over {len(values)} runs"
    )


def main() -> None:
    """Run both scenarios."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=1000)
    runs = parser.parse_args().runs
    with tempfile.TemporaryDirectory() as state:
        report("idle", [run_once(state) for _ in range(runs)])
        with ThreadPoolExecutor(PARALLEL) as pool:
            report(f"{PARALLEL} at once", list(pool.map(run_once, [state] * runs)))


if __name__ == "__main__":
    main()
