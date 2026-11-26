"""Files of `.code-factory/` that are text a person wrote: templates and agent instructions."""

import re

from code_factory.settings.models.kinds import TICKET_TYPES
from code_factory.settings.models.problems import Problem
from code_factory.settings.rules.config import TomlError, parse_toml
from code_factory.settings.rules.cross import inside_repository
from code_factory.settings.rules.lines import entry_line

TEMPLATE_BYTES = 64 * 1024
CONFIG_BYTES = 256 * 1024
TEMPLATES_FOLDER = ".code-factory/templates"
AGENTS_FOLDER = ".code-factory/agents"
DOCUMENT_TEMPLATES = ("requirements", "spec", "uat", "mock")
_STAGE = re.compile(r"[a-z][a-z0-9-]*")


def is_stage(name: str) -> bool:
    """Whether `name` can name a stage's instruction file: no path parts, no dot."""
    return _STAGE.fullmatch(name) is not None


def ticket_template_path(ticket_type: str) -> str | None:
    """The repository path of the template of a ticket type; None for a type there is none of."""
    return f"{TEMPLATES_FOLDER}/ticket-{ticket_type}.md" if ticket_type in TICKET_TYPES else None


def unreadable_message(limit: int) -> str:
    """Why a file is refused: not text, too big, or reached through a link."""
    return (
        f"is not a text file of at most {limit // 1024} KiB below the repository "
        "(a link is not followed)"
    )


def automation_templates(text: str) -> list[tuple[int, str]]:
    """Each automation's `template` path inside the repository, with its entry's index."""
    raw = parse_toml(text)
    entries = raw.get("automations") if not isinstance(raw, TomlError) else None
    if not isinstance(entries, list):
        return []
    found: list[tuple[int, str]] = []
    for index, entry in enumerate(entries):
        template: object = entry.get("template") if isinstance(entry, dict) else None
        if isinstance(template, str) and template.strip() and inside_repository(template.strip()):
            found.append((index, template.strip()))
    return found


def template_problem(path: str, text: str, index: int, template: str) -> Problem:
    """The problem of an automation template the board could not read, on its line."""
    return Problem(
        path,
        entry_line(text, "automations", index, "template"),
        f'automations.template: "{template}" {unreadable_message(TEMPLATE_BYTES)}',
    )
