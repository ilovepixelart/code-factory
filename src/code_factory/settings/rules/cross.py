"""What is wrong with a config.toml across keys: one key held to another, or to a path."""

from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

from code_factory.settings.rules.findings import Finding
from code_factory.settings.rules.lines import entry_line
from code_factory.settings.rules.secrets import (
    VALIDATION_HOME,
    Resolve,
    Unjudged,
    collapsed,
    container_mount_problem,
)

CONFIG_FOLDER = ".code-factory"


def _text(entry: dict[str, Any], key: str) -> str | None:
    value: object = entry.get(key)
    return value.strip() if isinstance(value, str) else None


def inside_repository(path: str) -> bool:
    """Whether `path` stays inside the repository: relative, no `..`."""
    parts = PurePosixPath(path).parts
    return bool(path) and PurePosixPath(path).is_absolute() is False and ".." not in parts


def _under_folder(file: str) -> bool:
    parts = PurePosixPath(file).parts
    return len(parts) > 1 and parts[0] == CONFIG_FOLDER and ".." not in parts


def _container_file(checks: dict[str, Any]) -> list[Finding]:
    file = checks.get("container_file")
    if not isinstance(file, str):
        return []
    found = []
    if not _under_folder(file):
        found.append(
            Finding(
                "checks",
                None,
                "container_file",
                f"checks.container_file: expected a file under {CONFIG_FOLDER}/",
            )
        )
    if "container" in checks:
        found.append(
            Finding(
                "checks",
                None,
                "container_file",
                "checks.container_file: set container or container_file, not both",
            )
        )
    return found


def _container_mounts(
    checks: dict[str, Any], homes: Sequence[PurePosixPath], resolve: Resolve
) -> list[Finding]:
    items = checks.get("container_mounts")
    if not isinstance(items, list):
        return []
    found: list[Finding] = []
    unjudged: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        try:
            why = container_mount_problem(item, homes, resolve)
        except Unjudged:
            unjudged.append(item)
            continue
        if why is not None:
            found.append(
                Finding("checks", None, "container_mounts", f"checks.container_mounts: {why}")
            )
    if unjudged:
        raise Unjudged(tuple(unjudged))
    return found


def _judge_sample(agents: dict[str, Any]) -> list[Finding]:
    if "judge_sample" in agents and "monthly_budget_usd" not in agents:
        return [
            Finding(
                "agents",
                None,
                "judge_sample",
                "agents.judge_sample: judge_sample needs monthly_budget_usd",
            )
        ]
    return []


def _name_problems(table: str, index: int, entry: dict[str, Any]) -> list[Finding]:
    if "name" not in entry:
        return [Finding(table, index, "name", f"{table}.name: required", whole_entry=True)]
    name = _text(entry, "name")
    if name is not None and ("@" in name or "\n" in name):
        message = f"{table}.name: must not contain @ or a line break"
        return [Finding(table, index, "name", message, whole_entry=True)]
    return []


def _automation(index: int, entry: dict[str, Any]) -> list[Finding]:
    def drop(key: str, message: str) -> Finding:
        return Finding("automations", index, key, message, whole_entry=True)

    found = _name_problems("automations", index, entry)
    if "title" not in entry:
        found.append(drop("title", "automations.title: required"))
    match ("every" in entry, "on" in entry):
        case (False, False):
            found.append(drop("name", "automations: set one trigger, every or on"))
        case (True, True):
            found.append(drop("on", "automations.on: an automation has one trigger, every or on"))
    if "body" in entry and "template" in entry:
        found.append(drop("template", "automations.template: set body or template, not both"))
    template = _text(entry, "template")
    if template is not None and template != "" and not inside_repository(template):
        found.append(
            drop("template", "automations.template: expected a path inside the repository")
        )
    return found


def _scorer(index: int, entry: dict[str, Any]) -> list[Finding]:
    found = _name_problems("scorers", index, entry)
    if "question" not in entry:
        found.append(
            Finding("scorers", index, "question", "scorers.question: required", whole_entry=True)
        )
    sample = entry.get("sample")
    if isinstance(sample, int | float) and not isinstance(sample, bool) and not 0 <= sample <= 1:
        found.append(
            Finding(
                "scorers",
                index,
                "sample",
                "scorers.sample: expected a number from 0 to 1",
                whole_entry=True,
            )
        )
    return found


def _repeated_names(table: str, entries: list[Any], text: str) -> list[Finding]:
    """Each entry whose name an earlier one took, naming that one's line."""
    first: dict[str, int] = {}
    found = []
    for index, entry in enumerate(entries):
        name = _text(entry, "name")
        if name is None or name == "":
            continue
        if name in first:
            line = entry_line(text, table, first[name], "name")
            message = f'{table}.name: "{name}" is already the name on line {line}'
            found.append(Finding(table, index, "name", message, whole_entry=True))
        else:
            first[name] = index
    return found


def _entries(raw: dict[str, Any], table: str) -> list[dict[str, Any]] | None:
    entries = raw.get(table)
    if isinstance(entries, list) and all(isinstance(entry, dict) for entry in entries):
        return entries
    return None


def cross_key_findings(
    raw: dict[str, Any],
    text: str,
    homes: Sequence[PurePosixPath] = (VALIDATION_HOME,),
    resolve: Resolve = collapsed,
) -> list[Finding]:
    """Findings across keys of a parsed config.toml, over the values as written."""
    found: list[Finding] = []
    checks = raw.get("checks")
    if isinstance(checks, dict):
        found += _container_file(checks) + _container_mounts(checks, homes, resolve)
    agents = raw.get("agents")
    if isinstance(agents, dict):
        found += _judge_sample(agents)
    for table, rule in (("automations", _automation), ("scorers", _scorer)):
        entries = _entries(raw, table)
        if entries is not None:
            for index, entry in enumerate(entries):
                found += rule(index, entry)
            found += _repeated_names(table, entries, text)
    return found
