"""The hook launcher as a runtime starts it, and a ticket tree with a real origin to judge it by."""

import contextlib
import http.server
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Self, override

import code_factory.hooks.adapters.hook as hook_module
from git_support import commit, git, make_repo

HOOK = Path(hook_module.__file__)
GOLDEN = Path(__file__).parent / "golden" / "hooks"
BRANCH = "ticket/cf-1"


@dataclass(frozen=True)
class Ran:
    """What a hook process did: its exit code, standard output and standard error."""

    code: int
    out: str
    err: str


def run_hook(  # noqa: PLR0913  # what a runtime sets for a hook process
    name: str,
    stdin: bytes | str,
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float = 20,
    flags: tuple[str, ...] = (),
) -> Ran:
    """Start `python -I -S <hook> <name>` as the runtime does, with `stdin` as the payload."""
    data = stdin.encode() if isinstance(stdin, str) else stdin
    clean = {k: v for k, v in os.environ.items() if not k.startswith("CODE_FACTORY_")}
    done = subprocess.run(  # noqa: S603  # our own interpreter and file
        [sys.executable, "-I", "-S", *flags, str(HOOK), name],
        input=data,
        capture_output=True,
        cwd=cwd,
        env={**clean, **(env or {})},
        timeout=timeout,
        check=False,
    )
    return Ran(done.returncode, done.stdout.decode(), done.stderr.decode())


def bash(command: str, cwd: Path) -> str:
    """The PreToolUse payload of a shell command run from `cwd`."""
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(cwd),
        }
    )


@dataclass(frozen=True)
class Tree:
    """A checkout, its ticket tree on `ticket/cf-1`, and the bare origin."""

    root: Path
    tree: Path


def ticket_tree(base: Path) -> Tree:
    """The tree of CF-1 with one commit the board has pushed to origin."""
    root = make_repo(base)
    tree = root / ".code-factory" / "worktrees" / "CF-1"
    git(root, "worktree", "add", "-q", "-b", BRANCH, str(tree))
    commit(tree, "pushed", **{"notes.txt": "pushed\n"})
    git(tree, "push", "-q", "origin", BRANCH)
    return Tree(root, tree)


@dataclass
class Seen:
    """One request the fake board received."""

    path: str
    authorization: str
    content_type: str
    body: dict[str, object]


@dataclass
class Reply:
    """What the fake board answers to a path: a status, a body and a delay before it."""

    status: int = 200
    body: bytes = b""
    delay_s: float = 0.0
    endless: bool = False  # keeps writing 64 KiB chunks until the client goes away


class FakeBoard:
    """A loopback HTTP server that records requests and answers from a script; a thread owns it."""

    def __init__(self, replies: dict[str, Reply]) -> None:
        self.requests: list[Seen] = []
        board = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # the http.server hook
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                board.requests.append(
                    Seen(
                        self.path,
                        self.headers.get("Authorization", ""),
                        self.headers.get("Content-Type", ""),
                        json.loads(raw) if raw else {},
                    )
                )
                reply = replies.get(self.path, Reply(404))
                time.sleep(reply.delay_s)
                with contextlib.suppress(OSError):
                    self.send_response(reply.status)
                    self.send_header(
                        "Content-Length", str(1 << 40 if reply.endless else len(reply.body))
                    )
                    self.end_headers()
                    self.wfile.write(reply.body)
                    while reply.endless:
                        self.wfile.write(b"x" * 65_536)

            @override
            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def board_env(url: str, token: str = "cfr_" + "t" * 43) -> dict[str, str]:  # a fixture
    """The environment a run's hooks start with."""
    return {"CODE_FACTORY_URL": url, "CODE_FACTORY_MCP_TOKEN": token}
