"""Check the test delta and select an inexpensive first pass from the branch's merge base."""

import argparse
import ast
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

SCRIPT_TEST = re.compile(r"""\b(?:test|it|describe)\s*(?:\.\w+\s*)?\(\s*(['"`])([^\n]+?)\1\s*,""")
SCRIPT_SKIP = re.compile(
    r"\b(?:test|it|describe)\s*\.\s*(skip(?:If)?|todo|fails(?:If)?|fixme)\s*\("
)
PY_SKIP = re.compile(r"(?:^|\.)(?:skip|skipIf|skipUnless|skipif|xfail|skipTest)$")
ASSERTION = re.compile(r"^\s*(?:assert\b|expect\s*\(|(?:self\.)?assert[A-Z]\w*\s*\()")
ROOTS = ("src/code_factory/", "tests/", "web/src/")
INSTRUCTIONS = ("CLAUDE.md", "AGENTS.md")
INSTRUCTION_LINES = 100


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    """Read the repository with external diff drivers and replacement refs disabled."""
    return subprocess.run(  # noqa: S603  # git subcommands are dispatched internally
        ["git", "--no-replace-objects", *args],  # noqa: S607  # uses the caller's git
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=check,
    )


def baseline(requested: str | None) -> str:
    """Resolve the common ancestor without fetching or moving a branch."""
    ref = requested or os.environ.get("CODE_FACTORY_CHECKS_BASE")
    if ref is None:
        remote = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False)
        ref = remote.stdout.decode().strip() if remote.returncode == 0 else "main"
    tip = git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    return git("merge-base", "HEAD", tip.stdout.decode().strip()).stdout.decode().strip()


def paths(base: str) -> list[str]:
    """Both sides of moves, changes against the base, and local untracked input files."""
    diff = git(
        "diff", "--no-ext-diff", "--no-textconv", "--name-only", "--no-renames", "-z", base, "--"
    ).stdout
    new = git(
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        "--exclude=.claude/worktrees/",
        "--exclude=.code-factory/worktrees/",
    ).stdout
    return sorted({p.decode(errors="surrogateescape") for p in (diff + new).split(b"\0") if p})


def test_file(path: str) -> bool:
    """Recognize the Python, Vue unit, and browser test file conventions."""
    name = Path(path).name
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith(
        (".test.ts", ".spec.ts", ".test.js", ".spec.js")
    )


def previous(base: str, path: str) -> str:
    """The old test source, empty for a path newly added."""
    return git("show", f"{base}:{path}", check=False).stdout.decode(errors="replace")


def current(path: str) -> str:
    """The working-copy test source, empty for a removed path."""
    file = Path(path)
    if file.is_file() and not file.is_symlink():
        return file.read_text(encoding="utf-8", errors="replace")
    return ""


def _python_facts(text: str) -> tuple[Counter[str], Counter[str]]:
    tree = ast.parse(text)
    cases: Counter[str] = Counter()
    skips: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                cases[node.name] += 1
            for decorator in node.decorator_list:
                route = decorator.func if isinstance(decorator, ast.Call) else decorator
                if PY_SKIP.search(ast.unparse(route)):
                    skips[ast.unparse(decorator)] += 1
        if isinstance(node, ast.Call) and PY_SKIP.search(ast.unparse(node.func)):
            skips[ast.unparse(node)] += 1
    return cases, skips


def facts(path: str, text: str) -> tuple[Counter[str], Counter[str], int]:
    """Test identities, skip forms, and assertion-like source lines."""
    if path.endswith(".py"):
        cases, skips = _python_facts(text)
    else:
        cases = Counter(match[2] for match in SCRIPT_TEST.finditer(text))
        skips = Counter(match[1] for match in SCRIPT_SKIP.finditer(text))
    return cases, skips, sum(bool(ASSERTION.search(line)) for line in text.splitlines())


def review(base: str, changed: list[str]) -> int:
    """Block obvious removal and skip additions. Warn about assertion-count changes."""
    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    refused = False
    for path in filter(test_file, changed):
        old, no_skips, was = facts(path, previous(base, path))
        new, skipped, now = facts(path, current(path))
        before.update(old)
        after.update(new)
        if added := skipped - no_skips:
            refused = True
            for marker in sorted(added):
                print(f"Test delta: {path!r} adds a new skip or expected failure ({marker[:120]}).")
        if now < was:
            print(f"Warning: {path!r} has fewer assertion lines ({was} to {now}).")
    if deleted := before - after:
        refused = True
        for name in sorted(deleted):
            print(f"Test delta: test function or case {name!r} was deleted.")
    for path in INSTRUCTIONS:
        count = len(current(path).splitlines())
        if count > INSTRUCTION_LINES:
            print(f"Warning: {path} has {count} lines. Aim for 100 or fewer.")
    return int(refused)


def _module_tests(path: str) -> str | None:
    if path in {"scripts/gate_delta.py", "tests/test_gate_delta.py"}:
        target = "tests/test_gate_delta.py"
        return target if Path(target).is_file() and Path(path).is_file() else None
    if path.startswith(ROOTS[0]):
        module, _, rest = path.removeprefix(ROOTS[0]).partition("/")
        target = f"tests/{module}"
        if rest and module != "platform" and Path(target).is_dir():
            return target
    if (
        path.startswith(ROOTS[1])
        and "/" in path.removeprefix(ROOTS[1])
        and test_file(path)
        and re.fullmatch(r"[A-Za-z0-9_./-]+", path)
        and Path(path).is_file()
    ):
        return path
    return None


def affected(changed: list[str]) -> int:
    """Print safely selectable pytest paths and whether Vue needs its unit suite."""
    python: set[str] = set()
    vue = False
    for path in changed:
        if path.endswith(".md") or path in {".gitignore", ".env.example"}:
            continue
        if path.startswith(ROOTS[2]) and not path.startswith(
            ("web/src/test/", "web/src/generated/")
        ):
            vue = True
        elif (target := _module_tests(path)) is not None:
            python.add(target)
        else:
            print("full")
            return 0
    for path in sorted(python):
        print(f"python {path}")
    if vue:
        print("vue")
    return 0


def main() -> int:
    """Run the requested branch comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("review", "affected", "base", "lockfiles"))
    parser.add_argument(
        "--base", help="compare with this ref's merge base (default: origin/HEAD or main)"
    )
    args = parser.parse_args()
    try:
        base = baseline(args.base)
        if args.action == "base":
            print(base)
            return 0
        changed = paths(base)
        if args.action == "lockfiles":
            for path in ("uv.lock", "site/uv.lock", "web/pnpm-lock.yaml"):
                if path in changed:
                    print(path)
            return 0
        return review(base, changed) if args.action == "review" else affected(changed)
    except (OSError, subprocess.CalledProcessError, SyntaxError) as error:
        parser.exit(2, f"Cannot check the branch delta: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
