"""A quarantine entry names a known flaky test, and the gate reads the file by lines."""

from code_factory.settings.models.problems import Problem
from code_factory.settings.rules.entries import ExceptionEntry
from code_factory.settings.rules.tool_files import EXCEPTIONS_FILE


def _line_text(text: str, line: int) -> str:
    lines = text.splitlines()
    return lines[line - 1] if 0 < line <= len(lines) else ""


def quarantine_problems(text: str, entry: ExceptionEntry, exists: bool) -> list[Problem]:
    """What is wrong with a quarantine entry: its lines' shape, and a test no file defines.

    `test` and `expires` are written alone on their line as `test = "<name>"` and
    `expires = <date>`, since the checks module reads the file by lines.
    """
    shapes = (
        ("test", entry.name_line, f'test = "{entry.name}"', 'test = "<name>"'),
        (
            "expires",
            entry.expires_line,
            f"expires = {entry.expires.isoformat()}",
            "expires = <date>",
        ),
    )
    found = [
        Problem(
            EXCEPTIONS_FILE,
            line,
            f"{entry.at}.{key}: not written as {shape} alone on its line",
        )
        for key, line, written, shape in shapes
        if _line_text(text, line) != written
    ]
    if not exists:
        found.append(
            Problem(
                EXCEPTIONS_FILE, entry.name_line, f"{entry.name} names no test in a tracked file"
            )
        )
    return found


def definition_search(test: str) -> tuple[str, tuple[str, ...]]:
    """The text and the path patterns that find where a gate-named test is defined.

    A vitest name `<file> > <suite> > <title>` is found by its last title in a file whose path
    ends in the first part; a pytest node id `<file>.py::<Class>::<name>[<case>]` by
    `def <name>(` in that file; a nextest `<binary> <path>::<name>` by `fn <name>(` in a Rust file.
    """
    if " > " in test:
        file, _, rest = test.partition(" > ")
        return rest.rpartition(" > ")[2], (file, f"*/{file}")
    if "::" in test and test.partition("::")[0].endswith(".py"):
        file, _, rest = test.partition("::")
        name = rest.rpartition("::")[2].partition("[")[0]
        return f"def {name}(", (file, f"*/{file}")
    path = test.rpartition(" ")[2]
    return f"fn {path.rpartition('::')[2]}(", ("*.rs",)
