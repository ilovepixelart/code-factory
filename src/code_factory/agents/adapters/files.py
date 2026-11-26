"""Files the agents module reads: Claude Code's agent files, the codex login and run logs.

Every read runs in a worker thread under a capacity limiter of its own; nothing is written.
"""

import os
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.agents.models.claude_agents import ClaudeAgent, ClaudeAgentList, Unread
from code_factory.agents.rules.claude_agents import parse_claude_agent
from code_factory.platform.errors import BadRequestError

MAX_AGENT_FILE = 256 * 1024
MAX_FILES_PER_FOLDER = 1000
MAX_LOG = 64 * 1024 * 1024
TAIL_WINDOW = 1024 * 1024
_agent_files = anyio.CapacityLimiter(4)
_log_files = anyio.CapacityLimiter(2)


def _markdown_files(folder: Path) -> list[Path]:
    """Every `.md` file under `folder`, sorted by path; links are not followed."""
    found: list[Path] = []
    stack = [folder]
    while stack and len(found) < MAX_FILES_PER_FOLDER:
        current = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(Path(entry.path))
            elif entry.name.endswith(".md") and entry.is_file(follow_symlinks=False):
                found.append(Path(entry.path))
    return sorted(found)[:MAX_FILES_PER_FOLDER]


def _read_agent(path: Path, place: str) -> ClaudeAgent | Unread:
    shown = str(path)
    try:
        if path.stat().st_size > MAX_AGENT_FILE:
            return Unread(path=shown, why="too large")
        text = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return Unread(path=shown, why="does not read")
    try:
        name, description, model, tools = parse_claude_agent(text)
    except BadRequestError as why:
        return Unread(path=shown, why=str(why))
    return ClaudeAgent(
        name=name, description=description, model=model, tools=tools, place=place, path=shown
    )


def _list(global_agents: Path, projects: list[Path]) -> ClaudeAgentList:
    places: list[tuple[Path, str]] = []
    # Without a home folder there is no global one; a relative path would read the board's own.
    if global_agents.is_absolute():
        places.append((global_agents, "global"))
    for project in projects:
        for folder in (project, *project.parents):
            agents = folder / ".claude" / "agents"
            if agents != global_agents and all(agents != seen for seen, _ in places):
                places.append((agents, folder.name))
    agents: list[ClaudeAgent] = []
    unread: list[Unread] = []
    for folder, place in places:
        for path in _markdown_files(folder):
            read = _read_agent(path, place)
            if isinstance(read, ClaudeAgent):
                agents.append(read)
            else:
                unread.append(read)
    return ClaudeAgentList(agents=agents, unread=unread)


class ClaudeAgentFiles:
    """Lists Claude Code's own agent files, read only."""

    def __init__(self, claude_home: Path | None = None) -> None:
        self._home = claude_home

    async def find(self, projects: list[Path]) -> ClaudeAgentList:
        """The global agents, then those under `.claude/agents` of each project and its parents."""
        home = self._home if self._home is not None else default_claude_home()
        return await anyio.to_thread.run_sync(
            _list, home / "agents", projects, limiter=_agent_files
        )


def default_claude_home() -> Path:
    """Claude Code's own folder: `CLAUDE_CONFIG_DIR` when set, else `~/.claude`."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR", "")
    if configured:
        return Path(configured)
    try:
        return Path.home() / ".claude"
    except RuntimeError:
        return Path(".claude")


def _read_login(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None


class CodexLoginFile:
    """The owner's codex login file: `auth.json` in `CODEX_HOME`, else in `~/.codex`."""

    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder

    def path(self) -> Path:
        """Where the file is."""
        if self._folder is not None:
            return self._folder / "auth.json"
        configured = os.environ.get("CODEX_HOME", "")
        base = Path(configured) if configured else _home() / ".codex"
        return base / "auth.json"

    async def read(self) -> tuple[Path, str | None]:
        """The file's path and its text; None when it cannot be read."""
        path = self.path()
        return path, await anyio.to_thread.run_sync(_read_login, path, limiter=_log_files)


def _home() -> Path:
    try:
        return Path.home()
    except RuntimeError:
        return Path()


def _tail(path: Path) -> list[str] | None:
    """The lines of a run log's tail window; None for a link, a missing file or an oversize one."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOG:
            return None
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - TAIL_WINDOW))
            data = handle.read()
    except OSError:
        return None
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if size > TAIL_WINDOW and lines else lines


def _whole(path: Path) -> list[str] | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOG:
            return None
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def _stamped(path: Path) -> tuple[list[str], float] | None:
    """The lines of a run log and when it last grew, in epoch seconds; `None` as for `_whole`."""
    lines = _whole(path)
    if lines is None:
        return None
    try:
        return lines, path.stat().st_mtime
    except OSError:
        return None


class RunLogReader:
    """Reads a run log as lines for the pure readers; no process, no link, at most 64 MiB."""

    async def lines(self, path: Path) -> list[str] | None:
        """Every line of the log; None when it is a link, missing or over 64 MiB."""
        return await anyio.to_thread.run_sync(_whole, path, limiter=_log_files)

    async def tail(self, path: Path) -> list[str] | None:
        """The lines of the log's last mebibyte, the first partial one dropped."""
        return await anyio.to_thread.run_sync(_tail, path, limiter=_log_files)

    async def stamped(self, path: Path) -> tuple[list[str], float] | None:
        """Every line of the log and when it last grew; None as for `lines`."""
        return await anyio.to_thread.run_sync(_stamped, path, limiter=_log_files)
