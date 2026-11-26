"""Pure document rules: activity kinds, notes, and what each document must hold."""

import re

from code_factory.platform.errors import BadRequestError
from code_factory.tickets.models import DocumentName, Problem
from code_factory.tickets.rules.reviews import FINDING_KINDS, rule_problems

_WORD = r"[a-z][a-z0-9]*(_[a-z0-9]+)*"
_KIND = re.compile(rf"{_WORD}(\.{_WORD})*")
NOTE_LIMIT = 4000
COORDINATOR_EDIT = "coordinator_edit"


def check_kind(kind: str) -> str:
    """`kind` when it is lower-case words joined by `_`, in parts joined by `.` (`run.started`).

    `BadRequestError` for any other, and for a kind only the review writes: a finding's state is
    read from those records, so they are not appended by hand; nor is a coordinator edit, which
    the undo reads back as the value to write.
    """
    if not _KIND.fullmatch(kind):
        msg = (
            f"{kind!r} is not a record kind: write lower-case words joined by _, "
            "as in stage, or run.started"
        )
        raise BadRequestError(msg)
    if kind in FINDING_KINDS:
        raise BadRequestError(
            f"{kind} is written by the review: submit a review or close a finding"
        )
    if kind == COORDINATOR_EDIT:
        raise BadRequestError(f"{kind} is written by a coordinator's edit of the ticket")
    return kind


def check_note(text: str) -> str:
    """A note's text, stripped; `BadRequestError` when it is empty or too long."""
    note = text.strip()
    if not note:
        raise BadRequestError("a note needs text")
    if len(note) > NOTE_LIMIT:
        msg = f"a note is at most {NOTE_LIMIT} characters; it has {len(note)}, shorten it"
        raise BadRequestError(msg)
    return note


DOCUMENT_LIMIT = 100_000
_REQUIREMENTS_HEADING = "## Requirements"
_TABLE_COLUMNS = 3


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _requirement_problems(content: str) -> list[Problem]:
    lines = content.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == _REQUIREMENTS_HEADING)
    except StopIteration:
        return [Problem(line=0, message="requirements has no ## Requirements table")]
    rows = []
    for index in range(start + 1, len(lines)):
        line = lines[index].strip()
        if line.startswith("## "):
            break
        if line.startswith("|"):
            rows.append((index + 1, _cells(line)))
    body = rows[2:]  # the header row and the |---| row
    if not body:
        return [Problem(line=0, message="requirements has no ## Requirements table")]
    problems = []
    for count, (line_number, cells) in enumerate(body, start=1):
        if len(cells) < _TABLE_COLUMNS or not cells[-1]:
            message = f"requirements row {count} ({cells[0]}) has no named check"
            problems.append(Problem(line=line_number, message=message))
    return problems


def validate_document(name: DocumentName, content: str) -> list[Problem]:
    """What is wrong with `content` as the ticket's `name` document; empty when nothing is.

    Requirements need their `## Requirements` table with a named check on every row (a test's
    name, or `review` for one checked by reading); a review's rule tags hold plain names; the other
    documents are free markdown.
    """
    if name is DocumentName.REQUIREMENTS:
        return _requirement_problems(content)
    if name is DocumentName.REVIEW:
        return rule_problems(content)
    return []


BLAST_RADIUS = "## Blast radius"


def _section_text(content: str, heading: str) -> str | None:
    """The text under `heading` up to the next `## ` heading, stripped; `None` with no heading."""
    lines = content.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return None
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body).strip()


def build_gaps(requirements: str, spec: str) -> list[str]:
    """What the documents lack before Build may start; empty when they are ready.

    The requirements need their table with a named check on every row, and the spec a
    `## Blast radius` section saying what the change touches and what it could break.
    """
    gaps = [problem.message for problem in _requirement_problems(requirements)]
    radius = _section_text(spec, BLAST_RADIUS)
    if radius is None:
        gaps.append(f"spec has no {BLAST_RADIUS} section")
    elif not radius:
        gaps.append(f"spec's {BLAST_RADIUS} section is empty")
    return gaps


MOCK_LIMIT = 16 * 1024 * 1024
# Never SVG: opened as a page it can run script.
_MOCK_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}
_MOCK_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")


def mock_type(name: str) -> str | None:
    """The type a mock file is served as: from a plain file name's image extension, else `None`.

    A plain name is letters, digits, `.`, `_` and `-`, not starting with a dot: no path, so it
    names a file directly under the ticket's mock folder.
    """
    stem, dot, extension = name.rpartition(".")
    if not dot or not stem or _MOCK_NAME.fullmatch(name) is None:
        return None
    return _MOCK_TYPES.get(extension.lower())


def check_mock(name: str, size: int) -> str:
    """The content type of a mock file about to be kept; `BadRequestError` naming what is wrong."""
    content_type = mock_type(name)
    if content_type is None:
        msg = (
            f"{name!r} is not a mock file name: a plain file name (letters, digits, . _ -) "
            "ending in png, jpg, jpeg, gif or webp; a mock file is never an SVG"
        )
        raise BadRequestError(msg)
    if size == 0:
        raise BadRequestError(f"mock file {name} is empty: send the image's bytes")
    if size > MOCK_LIMIT:
        msg = f"a mock file is at most 16 MiB; {name} is {size} bytes, shrink the image"
        raise BadRequestError(msg)
    return content_type
