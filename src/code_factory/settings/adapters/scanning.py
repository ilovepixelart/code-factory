"""Helpers of the settings service that run in a worker thread or read the machine."""

from pathlib import Path, PurePosixPath

from code_factory.settings.models.problems import Problem
from code_factory.settings.rules import config_problems
from code_factory.settings.rules.secrets import VALIDATION_HOME, Resolve
from code_factory.settings.rules.templates import automation_templates


def home_folder(home: Path | None) -> PurePosixPath:
    """The home folder checks hold container mounts away from, apart from the synthetic one."""
    try:
        return PurePosixPath(home or Path.home())
    except RuntimeError:
        return VALIDATION_HOME


def scan_config(
    config_file: str, text: str, homes: tuple[PurePosixPath, ...], resolve: Resolve
) -> tuple[list[Problem], list[tuple[int, str]]]:
    """The problems of a config and its automation templates, in one worker-thread call."""
    return config_problems(config_file, text, homes, resolve), automation_templates(text)
