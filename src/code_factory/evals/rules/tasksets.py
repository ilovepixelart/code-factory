"""Task set files: names, parsing, quoting and the text appended to a set."""

import json
import re
import tomllib
from collections.abc import Mapping

from code_factory.evals.models import BuildTask, ReviewTask, Stage, TaskSet
from code_factory.platform.errors import BadRequestError

BUILD_HEADER = 'stage = "build"\n\n'
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_TICKET = re.compile(r"[A-Za-z0-9_-]+")
_TASK_FIELDS = ("id", "base", "prompt", "check")
_REVIEW_FIELDS = ("id", "ticket", "base", "head")


def set_name_ok(name: str) -> bool:
    """Whether `name` is a plain file name segment."""
    return _NAME.fullmatch(name) is not None


def _missing(entry: Mapping[str, object], fields: tuple[str, ...]) -> None:
    lacking = [f for f in fields if not isinstance(entry.get(f), str) or not entry.get(f)]
    if lacking:
        name = entry.get("id") if isinstance(entry.get("id"), str) and entry.get("id") else "?"
        msg = f"task {name} has no {', '.join(lacking)}"
        raise BadRequestError(msg)


def _review(entry: Mapping[str, object]) -> ReviewTask:
    _missing(entry, _REVIEW_FIELDS)
    ticket = str(entry["ticket"])
    if not _TICKET.fullmatch(ticket):
        msg = f"task {entry['id']}: {ticket} is not a ticket id"
        raise BadRequestError(msg)
    files = entry.get("files")
    return ReviewTask(
        id=str(entry["id"]),
        ticket=ticket,
        base=str(entry["base"]),
        head=str(entry["head"]),
        files=tuple(str(f) for f in files) if isinstance(files, list) else None,
        defect=str(entry.get("defect") or ""),
    )


def parse_task_set(text: str) -> TaskSet:
    """The set the TOML text describes; `BadRequestError` naming what is wrong."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        msg = f"the task set is not TOML: {error}"
        raise BadRequestError(msg) from error
    stage = str(data.get("stage", "build"))
    if stage not in {s.value for s in Stage}:
        msg = f"the set's stage {stage} is not spec, build or review"
        raise BadRequestError(msg)
    tasks = []
    for entry in data.get("task", []):
        _missing(entry, _TASK_FIELDS)
        tasks.append(BuildTask(**{f: str(entry[f]) for f in _TASK_FIELDS}))
    reviews = [_review(entry) for entry in data.get("review", [])]
    return TaskSet(stage=Stage(stage), tasks=tuple(tasks), reviews=tuple(reviews))


def toml_string(text: str) -> str:
    """A TOML basic string that reads back as `text`."""
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


def task_block(task_id: str, base: str, prompt: str, check: str) -> str:
    """The `[[task]]` entry appended for a build task."""
    pairs = (("id", task_id), ("base", base), ("prompt", prompt), ("check", check))
    return "[[task]]\n" + "".join(f"{k} = {toml_string(v)}\n" for k, v in pairs)


def escape_block(bug: str, cause: str, base: str, head: str, files: list[str]) -> str:
    """The `[[review]]` entry of an escape: the change that caused `bug`."""
    pairs = (("id", f"escape-{bug}"), ("ticket", cause), ("base", base), ("head", head))
    listed = ", ".join(toml_string(f) for f in sorted(files))
    body = "".join(f"{k} = {toml_string(v)}\n" for k, v in pairs)
    return f"[[review]]\n{body}defect = {toml_string(bug)}\nfiles = [{listed}]\n"


def append_text(existing: str, block: str, fresh_header: str) -> str:
    """What to append to a set holding `existing`: its separator, then `block`."""
    if not existing:
        return fresh_header + block
    return ("\n" if existing.endswith("\n") else "\n\n") + block
