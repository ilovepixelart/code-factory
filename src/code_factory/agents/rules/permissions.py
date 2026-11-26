"""Permission requests.

What a call would do, the standing rule that would allow it, the kinds the owner always allowed,
and what the board's policy settles without the owner.
"""

import json
import re
from pathlib import PurePosixPath
from typing import Any

WAIT_SECONDS = 540
SUMMARY_LENGTH = 300
SUGGEST_AFTER = 5
ESCALATE_AFTER = 3
SANDBOXED = "a command inside the run's sandbox"
BOARD_TOOLS = "mcp__code-factory__"
READ_ONLY_TOOL = "a read-only board tool"
# Reads that name no ticket, and reads of one ticket that count only for the run's own. A tool's
# readOnlyHint is the server's own claim: some read-only tools reach the network or every ticket.
BOARD_READS = ("search_memory", "whoami")
OWN_TICKET_READS = ("get_ticket", "read_document", "list_activity")
# A command with these can do anything after its first words, so it never becomes a rule; a line
# break is one of them, since a shell runs each line.
_COMPOUND = re.compile(r"[|&;<>`\n\r]|\$\(")
_SPLIT = re.compile(r"""[\s"'`;|&<>()]""")


def _shell_command(tool: str, call: object) -> str | None:
    command = call.get("command") if isinstance(call, dict) else None
    return command if tool == "Bash" and isinstance(command, str) else None


def _said(tool: str, call: object) -> str:
    command = _shell_command(tool, call)
    return command if command is not None else json.dumps(call, ensure_ascii=False)


def summary(tool: str, call: object) -> str:
    """What a call would do: a shell command as written, anything else as JSON, cut short."""
    return _said(tool, call)[:SUMMARY_LENGTH]


def shown_whole(tool: str, call: object) -> bool:
    """Whether `summary` shows all of a call, none of it cut off."""
    return len(_said(tool, call)) <= SUMMARY_LENGTH


def request_kind(tool: str, call: object) -> str | None:
    """The standing rule that would allow a call, or `None` for a compound shell command."""
    if tool != "Bash":
        return tool or None
    command = _shell_command(tool, call)
    if command is None or _COMPOUND.search(command):
        return None
    words = command.split()
    if not words:
        return None
    stem = words[:2] if len(words) > 1 and not words[1].startswith("-") else words[:1]
    return f"Bash({' '.join(stem)} *)"


def _scalar_text(value: object) -> str | None:
    return None if isinstance(value, list | dict) else str(value)


def standing_rules(text: str | None) -> list[str]:
    """The rules the owner adopted, in the order adopted, from a JSON array of texts."""
    try:
        rules = json.loads(text) if bool(text) else None
    except ValueError:
        return []
    if not isinstance(rules, list):
        return []
    return [said for rule in rules if (said := _scalar_text(rule)) is not None]


def answer_history(text: str) -> dict[str, tuple[int, int]]:
    """Per kind of request, how many answers allowed it and how many there were, in kind order."""
    counts: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        try:
            said = json.loads(line)
        except ValueError:
            continue
        if not isinstance(said, dict):
            continue
        kind = _scalar_text(said.get("kind")) or ""
        allowed, total = counts.get(kind, (0, 0))
        counts[kind] = (allowed + bool(said.get("allowed")), total + 1)
    return dict(sorted(counts.items()))


def suggestions(answers: str, rules: list[str]) -> list[tuple[str, int]]:
    """The kinds allowed every time, often enough, that are not standing rules yet."""
    return [
        (kind, total)
        for kind, (allowed, total) in answer_history(answers).items()
        if total >= SUGGEST_AFTER and allowed == total and kind not in rules
    ]


def _outside(path: str, tree: str) -> bool:
    return path.startswith("/") and not PurePosixPath(path).is_relative_to(tree)


def _reached(tool: str, call: object, main: str, tree: str) -> str | None:
    fields = call if isinstance(call, dict) else {}
    if tool == "Read":
        path = fields.get("file_path")
        return path if isinstance(path, str) and _outside(path, tree) else None
    command = _shell_command(tool, call)
    if command is None:
        return None
    return next(
        (
            word
            for word in _SPLIT.split(command)
            if _outside(word, tree) and PurePosixPath(word).is_relative_to(main)
        ),
        None,
    )


def outside_tree(tool: str, call: object, main: str, tree: str) -> str | None:
    """Why a run's request is refused at once as reaching outside its tree `tree`.

    A Read of any absolute path outside it, or a shell command naming a path of the main checkout
    `main` outside it; `None` for every other request, which goes on.
    """
    path = _reached(tool, call, main, tree)
    if path is None:
        return None
    where = PurePosixPath(path)
    if where.is_relative_to(main):
        same = PurePosixPath(tree) / where.relative_to(main)
        return f"{path} is outside your worktree; use {same}, the same file in this run's tree"
    return f"{path} is outside your worktree {tree}; use paths inside it"


def routine(tool: str, call: object, main: str, tree: str, ticket: str) -> tuple[bool, str] | None:
    """How the board's policy settles a request of the run of `ticket`; `None`: the owner's.

    Refused when its words reach outside the tree, allowed when it calls a board read the policy
    names. No file read is allowed here: the tool opens its path after the hook answers,
    following links, so the read is not confined to what a check could see.
    """
    if (words := outside_tree(tool, call, main, tree)) is not None:
        return False, words
    if not tool.startswith(BOARD_TOOLS):
        return None
    name = tool.removeprefix(BOARD_TOOLS)
    own = isinstance(call, dict) and call.get("ticket_id") == ticket
    if name in BOARD_READS or (name in OWN_TICKET_READS and own):
        return True, READ_ONLY_TOOL
    return None


def refused_in_a_row(decisions: list[dict[str, Any]]) -> int:
    """How many of a ticket's latest decisions, oldest first, in a row, the policy refused."""
    count = 0
    for decision in reversed(decisions):
        if decision.get("by") != "policy" or decision.get("decision") != "deny":
            break
        count += 1
    return count


def escalation(count: int, reason: str) -> str:
    """The note of a request the policy hands to the owner after `count` refusals in a row."""
    return f"the board's policy refused {count} requests in a row: {reason}"
