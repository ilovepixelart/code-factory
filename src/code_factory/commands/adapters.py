"""The settings file on disk: read, back up, replace only if nobody changed it meanwhile."""

import json
import time
from pathlib import Path

import anyio

from code_factory.platform.errors import BadRequestError, ConflictError


def settings_path(scope: str, project: Path) -> Path:
    """Where Claude Code reads the settings of the scope."""
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    name = "settings.local.json" if scope == "local" else "settings.json"
    return project / ".claude" / name


def _text_or_none(path: Path) -> str | None:
    return path.read_text() if path.exists() else None


def _write(path: Path, before: str | None, text: str) -> Path | None:
    """Back the old text up, then replace the file through a temporary one; the backup's path."""
    backup = None
    if before is not None:
        backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_text(before)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text)
    temporary.replace(path)
    return backup


class SettingsFile:
    """One settings file: its text as read, and a replace that refuses a changed file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._read: str | None = None

    async def load(self) -> object:
        """The settings object, `{}` for a missing file; `BadRequestError` for text not JSON."""
        self._read = await anyio.to_thread.run_sync(_text_or_none, self.path)
        if self._read is None or not self._read.strip():
            return {}
        try:
            return json.loads(self._read)
        except json.JSONDecodeError as error:
            msg = f"{self.path} is not JSON: {error}"
            raise BadRequestError(msg) from error

    async def replace(self, settings: object) -> Path | None:
        """Write the settings after backing the old file up; the backup's path."""
        now = await anyio.to_thread.run_sync(_text_or_none, self.path)
        if now != self._read:
            msg = f"{self.path} changed while it was being edited; run the command again"
            raise ConflictError(msg)
        text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
        return await anyio.to_thread.run_sync(_write, self.path, self._read, text)


async def folder_problem(path: Path) -> str | None:
    """Why `path` cannot be a repository's folder (missing, not a folder); None when it can."""
    found = anyio.Path(path)
    if not await found.exists():
        return "does not exist"
    if not await found.is_dir():
        return "is not a folder"
    return None
