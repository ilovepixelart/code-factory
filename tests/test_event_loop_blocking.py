"""No blocking call sits directly in an `async def` under `src/`.

The walk is lexical: `anyio.to_thread.run_sync(path.read_text)` passes a reference, not a call,
so wrapped work never appears in the async body; a sync helper that blocks is allowed because only
its async callers are checked. Refactor a finding into a sync helper run on a worker thread rather
than suppressing the test.
"""

import ast
from pathlib import Path
from typing import override

from repo_files import ROOT

_PATHLIB = frozenset({"read_bytes", "write_bytes", "read_text", "write_text", "open"})
_MODULE_ATTRS = {
    "time": frozenset({"sleep"}),
    "subprocess": frozenset({"run", "call", "check_call", "check_output", "Popen"}),
    "os": frozenset({"system", "popen", "waitpid"}),
    "requests": frozenset({"get", "post", "put", "patch", "delete", "head", "request"}),
    "socket": frozenset({"create_connection", "gethostbyname"}),
    "sqlite3": frozenset({"connect"}),
    "shutil": frozenset({"copy", "copy2", "copytree", "rmtree", "move"}),
}
_NAMES = frozenset({"open", "input"})


def blocking_calls(source: str) -> list[tuple[int, str]]:
    """Blocking calls lexically inside an `async def` of `source`: (line, label)."""
    findings: list[tuple[int, str]] = []
    scope: list[bool] = []  # True while the nearest enclosing function is async

    class Finder(ast.NodeVisitor):
        def _scoped(self, node: ast.AST, *, is_async: bool) -> None:
            scope.append(is_async)
            self.generic_visit(node)
            scope.pop()

        @override
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._scoped(node, is_async=True)

        @override
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._scoped(node, is_async=False)

        @override
        def visit_Lambda(self, node: ast.Lambda) -> None:
            self._scoped(node, is_async=False)

        @override
        def visit_Call(self, node: ast.Call) -> None:
            if scope and scope[-1]:
                label = _label(node.func)
                if label is not None:
                    findings.append((node.lineno, label))
            self.generic_visit(node)

    Finder().visit(ast.parse(source))
    return findings


def _label(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name) and func.id in _NAMES:
        return f"{func.id}(...)"
    if isinstance(func, ast.Attribute):
        if func.attr in _PATHLIB:
            return f".{func.attr}(...)"
        if isinstance(func.value, ast.Name) and func.attr in _MODULE_ATTRS.get(func.value.id, ()):
            return f"{func.value.id}.{func.attr}(...)"
    return None


def test_the_guard_flags_blocking_calls_and_lets_wrapped_work_through() -> None:
    source = """
import time, subprocess
from pathlib import Path
import anyio

async def bad():
    time.sleep(1)
    subprocess.run(["ls"])
    Path("x").read_text()
    open("f")

async def good(path):
    await anyio.to_thread.run_sync(path.read_text)
    await anyio.sleep(1)

def sync_helper(path):
    time.sleep(1)
    return path.read_text()
"""
    assert blocking_calls(source) == [
        (7, "time.sleep(...)"),
        (8, "subprocess.run(...)"),
        (9, ".read_text(...)"),
        (10, "open(...)"),
    ]


def test_no_blocking_call_runs_on_the_event_loop() -> None:
    violations = [
        f"{path.relative_to(ROOT)}:{line} {label}"
        for path in sorted(Path(ROOT / "src").rglob("*.py"))
        for line, label in blocking_calls(path.read_text(encoding="utf-8"))
    ]
    assert not violations, "blocking call in `async def`:\n" + "\n".join(violations)
