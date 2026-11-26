"""A search result as the Memory page shows it: the snippet as text and the address it opens."""

import re
from collections.abc import Sequence
from urllib.parse import quote

from code_factory.memory.models import MemoryEntry

TOKENS = 12
ELLIPSIS = "..."
_TOKEN = re.compile(r"[^\W_]+")
_REMOTES = ("git@github.com:", "https://github.com/", "ssh://git@github.com/")
_MARKS = ("- ", "* ", "+ ")


def _is_syntax(line: str) -> bool:
    """A code fence, or a line of only `-`, `|`, `:` and spaces that holds a `-`: a rule."""
    ruled = "-" in line and all(char in "-|: " for char in line)
    return line.startswith(("```", "~~~")) or ruled


def _strip_marks(line: str) -> str:
    unquoted = line.lstrip("#>").lstrip()
    if len(unquoted) < len(line):
        return unquoted
    for mark in _MARKS:
        if line.startswith(mark):
            return line.removeprefix(mark)
    digits = len(line) - len(line.lstrip("0123456789"))
    rest = line[digits:]
    return rest.removeprefix(". ") if digits and rest.startswith(". ") else line


def plain_snippet(text: str) -> str:
    """A snippet cut from markdown as text.

    Fence, table separator and rule lines are dropped, as are the marks of headings, quotes and
    lists, and pipes, backticks and asterisks; the lines are joined by single spaces.
    """
    kept = [
        _strip_marks(line).replace("|", " ").replace("`", "").replace("*", "")
        for line in (raw.strip() for raw in text.splitlines())
        if not _is_syntax(line)
    ]
    return " ".join(" ".join(kept).split())


def github_web(remote: str) -> str | None:
    """The repository's address on GitHub from its `origin` remote over ssh or https."""
    remote = remote.strip()
    for prefix in _REMOTES:
        if remote.startswith(prefix):
            name = remote.removeprefix(prefix).removesuffix(".git")
            return f"https://github.com/{name}" if name else None
    return None


def _component(text: str) -> str:
    return quote(text, safe="-_.!~*'()")


def address(repository: str, path: str, web: str) -> str:
    """What a result at `path` opens, or empty when it opens nothing.

    The ticket's page, the entry on the Memory page, or the file on GitHub when `web` is known.
    """
    if path.startswith("tickets/") and "/" in (rest := path.removeprefix("tickets/")):
        return f"/tickets/{_component(repository)}/{_component(rest.split('/', maxsplit=1)[0])}"
    if path.startswith("memory/"):
        return f"#{path.removeprefix('memory/')}"
    if not web:
        return ""
    return f"{web}/blob/HEAD/{'/'.join(_component(part) for part in path.split('/'))}"


def snippet(text: str, words: Sequence[str], tokens: int = TOKENS) -> str:
    """A window of `tokens` words of the text holding the most of `words`, the first of equals.

    `...` marks where the text was cut.
    """
    found = list(_TOKEN.finditer(text))
    if not found:
        return ""
    wanted = set(words)
    hits = [match.group().lower() in wanted for match in found]
    starts = range(max(len(found) - tokens, 0) + 1)
    best = max(starts, key=lambda at: (sum(hits[at : at + tokens]), -at))
    window = found[best : best + tokens]
    cut_start = ELLIPSIS if best > 0 else ""
    cut_end = ELLIPSIS if best + len(window) < len(found) else ""
    return f"{cut_start}{text[window[0].start() : window[-1].end()]}{cut_end}"


def entry_text(entry: MemoryEntry) -> str:
    """What the knowledge search reads of an entry.

    Its set fields as `name: value` lines, then the statement.
    """
    fields = {
        "kind": entry.kind,
        "date": entry.date.isoformat(),
        "source": entry.source,
        "why": entry.why,
        "scope": entry.scope,
        "supersedes": ", ".join(entry.supersedes),
        "expires": entry.expires,
        "until": entry.until,
        "cites": ", ".join(entry.cites),
        "reviewed": entry.reviewed,
    }
    lines = [f"{name}: {value}" for name, value in fields.items() if value]
    return "\n".join([*lines, entry.statement])
