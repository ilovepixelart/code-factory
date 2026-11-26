"""config.toml held to its model: the report, and the lenient reading the other modules use.

Both come from the same findings. A finding names what is wrong (a table, a key, a list entry);
the report prints each with its line, the lenient reading drops what each names and reads the rest.
"""

import copy
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from pydantic import ValidationError

from code_factory.settings.models.config import RepositoryConfig
from code_factory.settings.models.problems import Problem
from code_factory.settings.rules.cross import cross_key_findings
from code_factory.settings.rules.findings import LISTS, Finding
from code_factory.settings.rules.lines import entry_line, header_line, key_line
from code_factory.settings.rules.secrets import VALIDATION_HOME, Resolve, collapsed

_AT_LINE = re.compile(r"at line (\d+)")
_MODEL_ERROR_TYPES = {"setting", "extra_forbidden"}


@dataclass(frozen=True)
class TomlError:
    """TOML that does not parse: tomllib's message and the line it names (0 when it names none)."""

    message: str
    line: int


def parse_toml(text: str) -> dict[str, Any] | TomlError:
    """The parsed table, or why it did not parse."""
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        found = _AT_LINE.search(str(error))
        return TomlError(str(error), int(found.group(1)) if found else 0)
    except RecursionError:
        return TomlError("nested too deeply to read", 0)
    except ValueError as error:  # an integer past Python's digit limit
        return TomlError(str(error), 0)


def _finding(error: Any) -> Finding | None:  # noqa: ANN401  # pydantic's ErrorDetails
    loc = error["loc"]
    table = str(loc[0])
    kind = error["type"]
    if table in LISTS:
        if kind not in _MODEL_ERROR_TYPES or len(loc) == 1:
            return Finding(table, None, None, f"{table}: expected a list of tables")
        index, key = loc[1], str(loc[2])
    elif len(loc) == 1:
        if kind == "extra_forbidden":
            return Finding(table, None, None, f"{table}: unknown table", at_header=True)
        return Finding(table, None, None, f"{table}: expected a table")
    else:
        index, key = None, str(loc[1])
    why = "unknown field" if kind == "extra_forbidden" else error["msg"]
    # An automation or scorer with any key off is not read at all; a recurring entry loses the key.
    return Finding(
        table, index, key, f"{table}.{key}: {why}", whole_entry=table in {"automations", "scorers"}
    )


def model_findings(raw: dict[str, Any]) -> list[Finding]:
    """Each way `raw` is off the model of the tables and lists, deduplicated."""
    try:
        RepositoryConfig.model_validate(raw)
    except ValidationError as error:
        found = (_finding(item) for item in error.errors(include_url=False))
        return list(dict.fromkeys(f for f in found if f is not None))
    return []


def findings(
    raw: dict[str, Any],
    text: str,
    homes: Sequence[PurePosixPath] = (VALIDATION_HOME,),
    resolve: Resolve = collapsed,
) -> list[Finding]:
    """Every finding of a parsed config.toml: the model's, then those across keys."""
    return [*model_findings(raw), *cross_key_findings(raw, text, homes, resolve)]


def _line(text: str, finding: Finding) -> int:
    key = finding.line_key or finding.key
    if key is None:
        return header_line(text, finding.table) if finding.at_header else 0
    if finding.index is not None:
        return entry_line(text, finding.table, finding.index, key)
    return key_line(text, finding.table, key)


def config_problems(
    path: str,
    text: str,
    homes: Sequence[PurePosixPath] = (VALIDATION_HOME,),
    resolve: Resolve = collapsed,
) -> list[Problem]:
    """Every way `text` is off the model of config.toml, sorted by line then message."""
    raw = parse_toml(text)
    if isinstance(raw, TomlError):
        return [Problem(path, raw.line, f"toml: {raw.message}")]
    return sorted(
        Problem(path, _line(text, f), f.message) for f in findings(raw, text, homes, resolve)
    )


def _without(raw: dict[str, Any], found: list[Finding]) -> dict[str, Any]:
    """`raw` minus everything the findings name."""
    kept = {table: value for table, value in raw.items() if isinstance(value, dict | list)}
    dropped_entries: dict[str, set[int]] = {}
    for item in found:
        value = kept.get(item.table)
        if item.index is None and isinstance(value, dict):
            if item.key is None:
                del kept[item.table]
            else:
                value.pop(item.key, None)
        elif item.index is not None and isinstance(value, list):
            if item.whole_entry:
                dropped_entries.setdefault(item.table, set()).add(item.index)
            elif item.key is not None:
                value[item.index].pop(item.key, None)
        elif item.key is None:
            kept.pop(item.table, None)
    for table, indexes in dropped_entries.items():
        if table in kept:
            kept[table] = [e for i, e in enumerate(kept[table]) if i not in indexes]
    return kept


def lenient_config(
    text: str,
    homes: Sequence[PurePosixPath] = (VALIDATION_HOME,),
    resolve: Resolve = collapsed,
) -> RepositoryConfig:
    """What `text` says, with everything a finding names dropped; never raises."""
    raw = parse_toml(text)
    if isinstance(raw, TomlError):
        return RepositoryConfig()
    raw = copy.deepcopy(raw)
    kept = _without(raw, findings(raw, text, homes, resolve))
    try:
        return RepositoryConfig.model_validate(kept)
    except ValidationError:
        return RepositoryConfig()


def names_container_mounts(text: str) -> bool:
    """Whether the parsed config names `container_mounts`, however its key is spelled."""
    raw = parse_toml(text)
    checks = raw.get("checks") if isinstance(raw, dict) else None
    return isinstance(checks, dict) and "container_mounts" in checks


def loaded_config(
    text: str, homes: Sequence[PurePosixPath], resolve: Resolve
) -> tuple[RepositoryConfig, bool]:
    """`lenient_config` and whether the file names mounts, whose judgement depends on the disk."""
    return lenient_config(text, homes, resolve), names_container_mounts(text)
