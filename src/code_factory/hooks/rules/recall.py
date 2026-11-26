"""The text recall hands a session, cut to its cap.

Heading, memory lines, the line saying what the memory budget left out, notices, the ticket's
lines and the index of archived entries. Sizes are characters, a line counting its line end.
"""

from code_factory.hooks.models import RecalledText, RecallParts

CAP = 10_000
TITLE_CHARS = 60
HEADING = "code-factory: read again at the start of this session."
MEMORY_HEADING = "Standing rules, decisions and lessons, each with why:"
LEFT_OUT = (
    "Left out over the memory budget of 8,000 characters (read them with the search_memory tool): "
)
INDEX_HEADING = "Archived memory, not loaded: read one with the search_memory tool (id: title):"


def _size(line: str) -> int:
    return len(line) + 1


def title(line: str) -> str:
    """The statement of a memory line, cut to 60 characters."""
    statement = line.removeprefix("- ")
    return statement.split(" Why: ", maxsplit=1)[0][:TITLE_CHARS]


def ticket_lines(  # noqa: PLR0913  # the five facts a ticket's lines are made of
    ticket_id: str,
    ticket_title: str,
    stage: str,
    branch: str,
    *,
    requirements: list[str],
    role_rules: list[str],
) -> list[str]:
    """The ticket on the branch, its requirements rows when it has any, then the role's rules."""
    head = f"Ticket on this branch: {ticket_id} {ticket_title} (stage: {stage}, branch {branch})"
    return [head, *(["Requirements:", *requirements] if requirements else []), *role_rules]


def _left_line(parts: RecallParts, kept: int, room: int) -> str | None:
    """The left-out line once the first `kept` memory lines stay: titles when they fit `room`."""
    left = [title(line) for _, line in [*parts.memory[kept:], *parts.left]]
    if not left:
        return None
    named = LEFT_OUT + "; ".join(left)
    return named if _size(named) <= room else f"{LEFT_OUT}{len(left)} entries"


def _memory_size(parts: RecallParts, kept: int) -> int:
    if kept == 0:
        return 0
    return _size(MEMORY_HEADING) + sum(_size(line) for _, line in parts.memory[:kept])


def _index_lines(index: list[str], room: int) -> list[str]:
    """The heading, as many entries as fit and a count of the rest; none when not even that fits."""
    for kept in range(len(index), -1, -1):
        rest = len(index) - kept
        more = [f"{rest} more archived entries: search_memory finds them."] if rest else []
        lines = [INDEX_HEADING, *index[:kept], *more]
        if sum(_size(line) for line in lines) <= room:
            return lines if index else []
    return []


def _memory_kept(parts: RecallParts, room: int) -> int:
    """How many memory lines stay: the most that fit with the left-out line for the rest."""
    kept = 0
    for count in range(len(parts.memory) + 1):
        remaining = room - _memory_size(parts, count)
        line = _left_line(parts, count, remaining)
        if remaining >= 0 and (line is None or _size(line) <= remaining):
            kept = count
    return kept


def within(parts: RecallParts, cap: int = CAP) -> RecalledText:
    """The recall's text within `cap`.

    Every ticket line that fits stays first, in order; then as many memory lines, in load order,
    as fit together with the line naming what is left out for the rest.
    """
    fixed = _size(HEADING) + sum(_size(n) for n in parts.notices)
    fixed += _size(parts.overflow) if parts.overflow is not None else 0
    reserve = _size(line) if (line := _left_line(parts, 0, 0)) is not None else 0
    room = max(cap - fixed - reserve, 0)
    ticket_kept = 0
    for line in parts.ticket:
        if _size(line) > room:
            break
        room -= _size(line)
        ticket_kept += 1
    room += reserve
    kept = _memory_kept(parts, room)
    left = _left_line(parts, kept, room - _memory_size(parts, kept))
    lines = [
        HEADING,
        *([MEMORY_HEADING] if kept else []),
        *(line for _, line in parts.memory[:kept]),
        *([parts.overflow] if parts.overflow is not None else []),
        *([left] if left is not None else []),
        *parts.notices,
        *parts.ticket[:ticket_kept],
    ]
    used = sum(_size(line) for line in lines)
    lines.extend(_index_lines(parts.index, max(cap - used, 0)))
    return RecalledText(text="\n".join(lines) + "\n", memory_kept=kept, ticket_kept=ticket_kept)
