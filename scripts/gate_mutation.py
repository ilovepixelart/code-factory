"""Warn when focused pytest suites miss small mutations to changed Python lines."""

import argparse
import ast
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from gate_coverage import changed_lines, production
from gate_delta import git, paths

MAX_MUTATIONS = 8
TOTAL_SECONDS = 180
SUITE_SECONDS = 45


@dataclass(frozen=True)
class Mutation:
    """A single expression at its original byte columns."""

    line: int
    start: int
    end: int
    replacement: bytes

    def apply(self, original: bytes) -> bytes:
        """Replace only this expression and preserve every other source line."""
        lines = original.splitlines(keepends=True)
        line = lines[self.line - 1]
        lines[self.line - 1] = line[: self.start] + self.replacement + line[self.end :]
        return b"".join(lines)


def mutations(data: bytes, changed: set[int]) -> list[Mutation]:
    """Flip boolean literals and complement comparisons on changed single lines."""
    result = []
    lines = data.splitlines()
    for node in ast.walk(ast.parse(data.decode("utf-8"))):
        if not isinstance(node, (ast.Compare, ast.Constant)) or node.lineno not in changed:
            continue
        if node.end_lineno != node.lineno or node.end_col_offset is None:
            continue
        if isinstance(node, ast.Constant) and not isinstance(node.value, bool):
            continue
        original = lines[node.lineno - 1][node.col_offset : node.end_col_offset]
        replacement = b"(not (" + original + b"))"
        result.append(Mutation(node.lineno, node.col_offset, node.end_col_offset, replacement))
    return sorted(result, key=lambda mutation: (mutation.line, mutation.start))


def run_tests(snapshot: Path, suite: str, deadline: float) -> int | None:
    """Run one bounded test suite against the disposable copy."""
    remaining = min(SUITE_SECONDS, deadline - time.monotonic())
    if remaining <= 0:
        return None
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTEST_ADDOPTS", None)
    entries = [str(snapshot / "src")]
    if env.get("PYTHONPATH"):
        entries.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(entries)
    try:
        return subprocess.run(  # noqa: S603  # a selected in-repo test directory, no shell
            [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "--", suite],
            cwd=snapshot,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=remaining,
        ).returncode
    except subprocess.TimeoutExpired:
        return None


def candidates(base: str) -> list[tuple[str, str, Mutation]]:
    """Find changes with a matching package test suite."""
    result = []
    for path in paths(base):
        file = Path(path)
        if not production(path) or file.suffix != ".py" or not file.is_file() or file.is_symlink():
            continue
        if git(
            "--literal-pathspecs", "ls-files", "--error-unmatch", "--", path, check=False
        ).returncode:
            continue
        module = file.relative_to("src/code_factory").parts[0]
        suite = f"tests/{module}"
        if Path(suite).is_dir():
            result.extend(
                (path, suite, mutation)
                for mutation in mutations(file.read_bytes(), changed_lines(base, path))
            )
    return result


def assess(base: str) -> None:
    """Check a clean commit in a clone and report surviving or inconclusive samples."""
    head = git("rev-parse", "--verify", "HEAD").stdout.decode().strip()
    if git("status", "--porcelain", "--untracked-files=no").stdout:
        print("Mutation warning: commit changes before checking the merge candidate.")
        return
    selected = candidates(base)
    if not selected:
        print("Mutation: no changed expressions with a matching Python test suite.")
        return
    deadline = time.monotonic() + TOTAL_SECONDS
    with tempfile.TemporaryDirectory(prefix="code-factory-mutation-") as directory:
        snapshot = Path(directory) / "checkout"
        git("clone", "--quiet", "--shared", "--no-checkout", "--", str(Path.cwd()), str(snapshot))
        git("-C", str(snapshot), "remote", "remove", "origin")
        git("-C", str(snapshot), "checkout", "--quiet", "--detach", head)
        if not (snapshot / "src/code_factory/__init__.py").is_file():
            print("Mutation warning: the disposable checkout has no importable source package.")
            return
        baseline: dict[str, int | None] = {}
        for path, suite, mutation in selected[:MAX_MUTATIONS]:
            if suite not in baseline:
                baseline[suite] = run_tests(snapshot, suite, deadline)
            if baseline[suite] != 0:
                print(
                    f"Mutation warning: {path}:{mutation.line} inconclusive "
                    "(baseline did not pass)."
                )
                continue
            target = snapshot / path
            original = target.read_bytes()
            try:
                target.write_bytes(mutation.apply(original))
                outcome = run_tests(snapshot, suite, deadline)
            finally:
                target.write_bytes(original)
            match outcome:
                case 0:
                    print(f"Mutation warning: {path}:{mutation.line} survived.")
                case 1:
                    print(f"Mutation: {path}:{mutation.line} was caught by {suite}.")
                case _:
                    print(f"Mutation warning: {path}:{mutation.line} inconclusive.")
    if len(selected) > MAX_MUTATIONS:
        print(f"Mutation: sampled {MAX_MUTATIONS} of {len(selected)} changed expressions.")


def main() -> int:
    """Make mutation findings advisory and expose setup errors as warnings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    args = parser.parse_args()
    try:
        assess(args.base)
    except OSError, SyntaxError, UnicodeError, subprocess.SubprocessError:
        print("Mutation warning: the disposable checkout or its test inputs could not be read.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
