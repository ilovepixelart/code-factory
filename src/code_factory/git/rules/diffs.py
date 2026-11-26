"""A unified diff read into files and lines for the ticket page."""

import re

from code_factory.git.models import DIFF_LIMIT, Changes, FileChange, Line

_HUNK = re.compile(r"^@@ -[0-9]+(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@")
_KINDS = {"+": "added", "-": "removed", " ": "kept"}


def _lines(text: str) -> list[str]:
    """Split on newlines only: git ends a line with one, a form feed or CR inside is content."""
    parts = text.split("\n")
    complete = parts[:-1]
    last = parts[-1]
    return [part.removesuffix("\r") for part in complete] + ([last] if last else [])


def _count(group: str | None) -> int:
    return 1 if group is None else int(group)


def parse_diff(text: str, limit: int = DIFF_LIMIT) -> Changes:  # one pass over the lines
    """Read a unified diff into files and at most `limit` lines.

    A hunk runs for the old and new line counts its header gives; only outside one are `---` and
    `+++` file headers.
    """
    files: list[tuple[str, list[Line]]] = []
    number = count = old_left = new_left = 0
    for raw in _lines(text):
        if old_left <= 0 and new_left <= 0:
            if hunk := _HUNK.match(raw):
                number = int(hunk[2])
                old_left, new_left = _count(hunk[1]), _count(hunk[3])
            elif raw.startswith("+++ "):
                path = raw[4:].removeprefix("b/")
                files.append(("" if path == "/dev/null" else path, []))
            continue
        kind = _KINDS.get(raw[:1])
        if kind is None:
            continue
        old_left -= kind != "added"
        new_left -= kind != "removed"
        if not files:
            continue
        if count == limit:
            return _result(files, cut=True)
        removed = kind == "removed"
        files[-1][1].append(Line(kind=kind, number=None if removed else number, text=raw[1:]))
        number += not removed
        count += 1
    return _result(files, cut=False)


def _result(files: list[tuple[str, list[Line]]], *, cut: bool) -> Changes:
    return Changes(files=[FileChange(path=path, lines=lines) for path, lines in files], cut=cut)
