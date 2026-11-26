"""A Claude Code agent file: a Markdown file whose YAML front matter names it."""

from typing import Any

import yaml

from code_factory.platform.errors import BadRequestError


def _front_matter(text: str) -> str | None:
    """The text between a first line `---` and the next line `---`; None without both."""
    rest = text.removeprefix("---\n") if text.startswith("---\n") else None
    if rest is None and text.startswith("---\r\n"):
        rest = text.removeprefix("---\r\n")
    if rest is None:
        return None
    kept: list[str] = []
    for line in rest.splitlines(keepends=True):
        if line.rstrip() == "---":
            return "".join(kept)
        kept.append(line)
    return None


def _text(fields: dict[str, Any], key: str) -> str | None:
    value = fields.get(key)
    return value if isinstance(value, str) else None


def _tools(value: object) -> list[str]:
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list):
        items = [item for item in value if isinstance(item, str)]
    else:
        items = []
    return [tool for tool in (item.strip() for item in items) if tool]


def parse_claude_agent(text: str) -> tuple[str, str, str, list[str]]:
    """The name, description, model and tools of an agent file's text.

    Only these fields are read; every other is Claude Code's alone.
    """
    front = _front_matter(text)
    if front is None:
        msg = "no front matter"
        raise BadRequestError(msg)
    try:
        loaded = yaml.safe_load(front)
    except yaml.YAMLError as error:
        msg = f"front matter: {error}".replace("\n", " ")
        raise BadRequestError(msg) from None
    fields: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
    name = _text(fields, "name")
    if name is None:
        msg = "name: missing"
        raise BadRequestError(msg)
    description = _text(fields, "description")
    if description is None:
        msg = "description: missing"
        raise BadRequestError(msg)
    return name, description, _text(fields, "model") or "", _tools(fields.get("tools"))
