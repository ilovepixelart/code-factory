"""The screen on what the board pushes and posts to a forge for an agent.

Code is read for secrets only, since code names hosts and phrases for good reasons; what the
board posts in words is read for secrets, links to hosts the repository does not list, and
instructions aimed at an agent. A finding names its kind and line, never what it found.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

import ada_url

from code_factory.platform.text.screen_links import link_lines
from code_factory.platform.text.screen_reading import instruction_lines, numbered, shown

# Key shapes no ordinary text has: provider and forge tokens of their full length (a forge's
# prefix is distinctive enough to find glued to a word, a provider's `sk-` is not), cloud access
# key ids and a private key's first line.
_SHAPES = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}",
        r"(?:gh[porsu]_|github_pat_|glpat-|xox[abps]-)[A-Za-z0-9_-]{20,}",
        r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
        r"\bAIza[0-9A-Za-z_-]{35}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    )
)
# A known secret shorter than this many bytes is not looked for: it would match ordinary words.
_SHORTEST_KNOWN = 8
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")


class Kind(StrEnum):
    """What a finding is."""

    SECRET = "secret"  # noqa: S105  # the name of a kind, not a credential
    LINK = "link"
    INSTRUCTION = "instruction"

    @property
    def named(self) -> str:
        """The kind as a reason names it."""
        return {
            Kind.SECRET: "a secret",
            Kind.LINK: "a link to an unlisted host",
            Kind.INSTRUCTION: "an instruction aimed at an agent",
        }[self]


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing the screen found, by kind and line (from 1); never the text it found."""

    kind: Kind
    line: int


def secrets(text: str, known: Iterable[str] = ()) -> list[Finding]:
    """The lines holding a key shape or one of the `known` values (the board's connection keys)."""
    values = [
        value
        for value in (item.strip() for item in known)
        if len(value.encode()) >= _SHORTEST_KNOWN
    ]
    return [
        Finding(Kind.SECRET, number)
        for number, line in numbered(text)
        if any(shape.search(line) for shape in _SHAPES) or any(value in line for value in values)
    ]


def words(text: str, known: Iterable[str], hosts: list[str]) -> list[Finding]:
    """Everything in the text the board must not post in words, in line order.

    Per line: its secrets, then its links to hosts not under one of `hosts`, then its
    instructions aimed at an agent; one finding of a kind per line.
    """
    found = secrets(text, known)
    found += [Finding(Kind.LINK, number) for number in link_lines(text, hosts)]
    found += [Finding(Kind.INSTRUCTION, number) for number in instruction_lines(text)]
    return sorted(found, key=lambda finding: finding.line)


def remote_host(remote: str) -> str | None:
    """The lowercase host a git remote names (`https://h/o/r`, `ssh://git@h/o/r`, `git@h:o/r.git`).

    None for a local path.
    """
    remote = remote.strip()
    if _SCHEME.match(remote):
        try:
            host = str(ada_url.parse_url(remote)["hostname"])
        except ValueError:
            return None
    elif ":" in remote:
        host = remote.split(":", 1)[0].rsplit("@", 1)[-1]
    else:
        return None
    return host.lower() if host and "/" not in host else None


__all__ = ["Finding", "Kind", "remote_host", "secrets", "shown", "words"]
