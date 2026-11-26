"""The hook launcher: what a coding agent's runtime starts as `python -I -S <this file> <name>`.

`rewrite` runs before every shell command of a run and `tell` after every tool result, so this
file starts fast: standard library only, no event loop, no `code_factory` import, and each import
is made at the step that needs it (a payload with no `git` in it never imports `json`). It is
synchronous on purpose: its printed answer is the point. Any failure prints nothing and exits 0,
so a hook never stops a run by itself failing; a refusal is an answer, not a failure.

`tell`, `permission` and `recall` are thin clients of the board over loopback HTTP, with the run's
bearer token in `CODE_FACTORY_MCP_TOKEN`; the board's address is `CODE_FACTORY_URL`.
"""

import sys
from types import ModuleType

MAX_BODY = 1 << 20
MAX_READ = MAX_BODY + 16_384  # the body and the head of its answer
CONNECT_S = 1.0
ANSWER_S = 5.0
PERMISSION_S = 600.0
GIT_CALL_S = 5.0
GIT_DEADLINE_S = 25.0
DEFAULT_URL = "http://127.0.0.1:4000"
LOOPBACK = ("127.0.0.1", "localhost", "[::1]")
TOKEN_VARIABLE = "CODE_FACTORY_MCP_TOKEN"  # noqa: S105  # a name, not a secret
URL_VARIABLE = "CODE_FACTORY_URL"
SANDBOX_VARIABLE = "CODE_FACTORY_SANDBOXED"


def _load_rules() -> tuple[ModuleType, ModuleType]:
    """The rewrite guard and the output rules, imported without importing the package.

    The package's `__init__` reads installed metadata, which `-S` cannot find, so the package name
    is bound to a bare module that points at the folder.
    """
    if "code_factory" not in sys.modules:
        from os.path import dirname  # noqa: PLC0415

        bare = ModuleType("code_factory")
        bare.__path__ = [dirname(dirname(dirname(__file__)))]  # noqa: PTH120  # pathlib costs start time
        sys.modules["code_factory"] = bare
    from code_factory.hooks.rules import output, rewrite_guard  # noqa: PLC0415

    return rewrite_guard, output


class BranchReader:
    """What origin holds of a tree's branch, read from the remote-tracking ref already there.

    Never fetches, and runs only `symbolic-ref`, `rev-parse` and `merge-base --is-ancestor`, with
    the repository's own programs switched off and the environment rebuilt from scratch (a run can
    set `GIT_DIR` and its like). A call that fails or times out reads as unknown.
    """

    def __init__(self, guard: ModuleType) -> None:
        import os  # noqa: PLC0415
        import time  # noqa: PLC0415

        self._guard = guard
        self._deadline = time.monotonic() + GIT_DEADLINE_S
        folders = [p for p in os.environ.get("PATH", "").split(":") if p.startswith("/")]
        self._env = {
            "PATH": ":".join(folders) or "/usr/bin:/bin",
            "HOME": os.environ.get("HOME", "/"),
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
        }
        self._branches: dict[str, tuple[str, str, bool] | None] = {}

    def _git(self, directory: str, *args: str) -> tuple[int, str] | None:
        import subprocess  # noqa: PLC0415
        import time  # noqa: PLC0415

        left = min(GIT_CALL_S, self._deadline - time.monotonic())
        if left <= 0:
            return None
        command = [
            "git", "-C", directory, "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            *args,
        ]  # fmt: skip
        try:
            done = subprocess.run(  # noqa: S603  # a fixed program with fixed read-only arguments
                command, capture_output=True, text=True, timeout=left, stdin=subprocess.DEVNULL,
                env=self._env, check=False,
            )  # fmt: skip
        except OSError, subprocess.SubprocessError:
            return None
        return done.returncode, done.stdout.strip()

    def _commit(self, directory: str, revision: str) -> str | None:
        if revision.startswith("-"):
            return None
        found = self._git(directory, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}")
        return found[1] if found is not None and found[0] == 0 and found[1] else None

    def _is_ancestor(self, directory: str, older: str, newer: str) -> bool | None:
        found = self._git(directory, "merge-base", "--is-ancestor", older, newer)
        return None if found is None else found[0] == 0

    def _branch(self, directory: str) -> tuple[str, str, bool] | None:
        """The checked-out branch, the tip origin holds of it and whether HEAD is under that tip."""
        if directory not in self._branches:
            self._branches[directory] = self._read_branch(directory)
        return self._branches[directory]

    def _read_branch(self, directory: str) -> tuple[str, str, bool] | None:
        named = self._git(directory, "symbolic-ref", "--quiet", "--short", "HEAD")
        if named is None or named[0] != 0 or not named[1]:
            return None
        tip = self._commit(directory, f"refs/remotes/origin/{named[1]}")
        if tip is None:
            return None
        return named[1], tip, bool(self._is_ancestor(directory, "HEAD", tip))

    def state(self, directory: str, revision: str | None) -> object | None:
        """The `BranchState` a rewrite in `directory` runs on; `None` when origin has no branch.

        `revision` is the commit the command moves to, when it names one.
        """
        found = self._branch(directory)
        if found is None:
            return None
        branch, tip, head_pushed = found
        target = None if revision is None else self._commit(directory, revision)
        keeps = None if target is None else self._is_ancestor(directory, tip, target)
        return self._guard.BranchState(branch, head_pushed=head_pushed, keeps_pushed=keeps)


def rewrite_hook(data: bytes) -> str | None:
    """The refusal to print for a PreToolUse payload, or `None` to allow the command."""
    if b"git" not in data:
        return None
    import json  # noqa: PLC0415

    payload = json.loads(data)
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return None
    given = payload.get("tool_input")
    command = given.get("command") if isinstance(given, dict) else None
    if not isinstance(command, str):
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        import os  # noqa: PLC0415

        cwd = os.getcwd()  # noqa: PTH109  # pathlib costs start time
    guard, output = _load_rules()
    reader = BranchReader(guard)
    for rewrite in guard.rewrites(command, cwd):
        if not guard.in_ticket_tree(rewrite.dir):
            continue
        state = (
            None if rewrite.action == guard.FORCE else reader.state(rewrite.dir, rewrite.revision())
        )
        reason = guard.refusal(rewrite, state)
        if reason is not None:
            return str(output.rewrite_denied(reason))
    return None


def _target(url: str) -> tuple[str, int] | None:
    """The host and port of a plain `http://` loopback address; nothing else is called."""
    if not url.startswith("http://"):
        return None
    authority = url[len("http://") :].split("/", 1)[0]
    host, port = authority, "80"
    if not authority.endswith("]") and ":" in authority:
        host, _, port = authority.rpartition(":")
    if host not in LOOPBACK or not port.isdigit():
        return None
    return host.strip("[]"), int(port)


class Board:
    """The board over loopback HTTP with a run's bearer token: one HTTP/1.0 request per call.

    A call that cannot be made, fails, times out or is not answered 200 with a JSON object gives
    `None`; nothing here raises to the hook.
    """

    def __init__(self) -> None:
        import os  # noqa: PLC0415

        self._token = os.environ.get(TOKEN_VARIABLE, "")
        self._target = _target(os.environ.get(URL_VARIABLE) or DEFAULT_URL)

    @property
    def configured(self) -> bool:
        """Whether a token and a loopback address are set."""
        control = any(ord(char) < 0x20 or ord(char) == 0x7F for char in self._token)  # noqa: PLR2004
        return bool(self._token) and not control and self._target is not None

    def post(
        self, path: str, document: dict[str, object], total_s: float
    ) -> dict[str, object] | None:
        """The JSON object the board answers to `document` with 200, within `total_s` seconds."""
        import json  # noqa: PLC0415
        import socket  # noqa: PLC0415
        import time  # noqa: PLC0415

        body = json.dumps(document).encode()
        if self._target is None or len(body) > MAX_BODY:
            return None
        host, port = self._target
        head = (
            f"POST {path} HTTP/1.0\r\nHost: {host}:{port}\r\n"
            f"Authorization: Bearer {self._token}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n"
        )
        deadline = time.monotonic() + total_s
        received = b""
        try:
            with socket.create_connection((host, port), timeout=CONNECT_S) as sock:
                sock.settimeout(max(deadline - time.monotonic(), 0.001))
                sock.sendall(head.encode() + body)
                while len(received) <= MAX_READ:
                    sock.settimeout(max(deadline - time.monotonic(), 0.001))
                    chunk = sock.recv(65_536)
                    if not chunk:
                        break
                    received += chunk
        except OSError:
            return None
        return _answer(received)


def _answer(received: bytes) -> dict[str, object] | None:
    import json  # noqa: PLC0415

    head, separator, body = received.partition(b"\r\n\r\n")
    status = head.split(b" ", 2)
    if not separator or len(status) < 2 or status[1] != b"200" or len(body) > MAX_BODY:  # noqa: PLR2004
        return None
    try:
        answer = json.loads(body)
    except ValueError:
        return None
    return {str(key): value for key, value in answer.items()} if isinstance(answer, dict) else None


def _object(data: bytes) -> dict[str, object] | None:
    import json  # noqa: PLC0415

    try:
        payload = json.loads(data)
    except ValueError:
        return None
    return (
        {str(key): value for key, value in payload.items()} if isinstance(payload, dict) else None
    )


def _printed(answer: dict[str, object] | None) -> bool:
    """Print the board's `output` text; whether there was one."""
    output = None if answer is None else answer.get("output")
    if not isinstance(output, str):
        return False
    _flush(output)
    return True


def tell_hook(data: bytes) -> None:
    """After a tool result: print what was said on the ticket, then confirm it was given.

    The printing comes first: a lost confirm repeats the news once, a lost print would lose it.
    """
    payload, board = _object(data), Board()
    if payload is None or not board.configured:
        return
    session = str(payload.get("session_id", ""))
    asked: dict[str, object] = {
        "session_id": session,
        "hook_event_name": str(payload.get("hook_event_name", "")),
    }
    answer = board.post("/api/hooks/tell", asked, ANSWER_S)
    if _printed(answer) and answer is not None and isinstance(answer.get("confirm"), dict):
        board.post(
            "/api/hooks/tell/confirm",
            {"session_id": session, "confirm": answer["confirm"]},
            ANSWER_S,
        )


def permission_hook(data: bytes) -> None:
    """A permission request: the board settles it, asking the owner when it has to."""
    import os  # noqa: PLC0415

    payload, board = _object(data), Board()
    if payload is None or not board.configured:
        return
    payload["sandboxed"] = os.environ.get(SANDBOX_VARIABLE) == "1"
    _printed(board.post("/api/hooks/permission", payload, PERMISSION_S))


def recall_hook(data: bytes) -> None:
    """At the start of a session: the standing rules and ticket the board hands back."""
    import os  # noqa: PLC0415

    payload, board = _object(data), Board()
    if payload is None or not board.configured:
        return
    cwd = payload.get("cwd")
    asked: dict[str, object] = {
        "cwd": cwd if isinstance(cwd, str) and cwd else os.getcwd(),  # noqa: PTH109  # pathlib costs start time
        "session_id": str(payload.get("session_id", "")),
    }
    _printed(board.post("/api/hooks/recall", asked, ANSWER_S))


HOOKS = {"tell": tell_hook, "permission": permission_hook, "recall": recall_hook}


def _flush(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    """Run the hook named in `argv[1]`; always 0."""
    name = argv[1] if len(argv) > 1 else ""
    try:
        data = sys.stdin.buffer.read()
        if name == "rewrite":
            denied = rewrite_hook(data)
            if denied is not None:
                _flush(denied)
        elif name in HOOKS and len(data) <= MAX_BODY:
            HOOKS[name](data)
    except Exception:  # noqa: BLE001, S110  # a hook that fails must not stop the run
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
