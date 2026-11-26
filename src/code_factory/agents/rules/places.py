"""Where a run may write and reach, and what the board starts it with.

The state folder in each of its forms, the lock folder of the gate's heavy steps, what the board
reads outside the sandbox, the hosts a worktree setup may reach, the identity of a run's commits,
the shell line that starts a command inside srt, and the one folder a codex program opens. Every
path arrives resolved by an adapter; the rules only join and compare them.
"""

import re
import shlex
from collections.abc import Callable, Sequence
from pathlib import PurePosixPath

from code_factory.agents.models.connections import ConnectionDefinition
from code_factory.agents.models.places import GitPlaces
from code_factory.agents.rules.connections import address
from code_factory.agents.rules.mounts import secret_paths
from code_factory.platform.errors import BadRequestError

AGENT_NAME = "code-factory agent"
AGENT_EMAIL = "agent@code-factory.invalid"
CODEX_HOME = ".codex"
# The worktree setup's hosts when the repository names none: the package registries, on the HTTPS
# port only, since an entry without a port admits every port of its host.
SANDBOX_DOMAINS = ("pypi.org:443", "files.pythonhosted.org:443", "registry.npmjs.org:443")
# An `allowed_domains` entry the sandbox proxy holds to its local address check: a host name ending
# in letters, optionally `*.` before it and a port after it. IP literals and names without a dot
# are decided by the list alone, and `localhost` names may resolve to loopback.
_HOST_NAME = re.compile(r"(?:\*\.)?(?:[A-Za-z0-9-]+\.)+([A-Za-z]+)(?::[0-9]+)?")
_PORT = 65535


def state_forms(home: str, resolved: str) -> list[str]:
    """The state folder as a run is given it, when absolute, and resolved, when that differs."""
    forms: list[str] = []
    for path in (home, resolved):
        if path.startswith("/") and path not in forms:
            forms.append(path)
    return forms


def lock_folder(home: str) -> str | None:
    """The folder of the gate's heavy-step lock: `<state>-locks`, beside the state folder `home`.

    `None` when `home` ends in no name.
    """
    where = PurePosixPath(home)
    return str(where.with_name(f"{where.name}-locks")) if where.name else None


def lock_folders(home: str, resolved_parent: str) -> list[str]:
    """The lock folder of an absolute `home`, and with its parent resolved when that differs.

    It is the one place outside its tree a run may write, so that its heavy steps wait their turn.
    It holds the lock and no key or token.
    """
    given = lock_folder(home)
    if given is None or not home.startswith("/"):
        return []
    resolved = str(PurePosixPath(resolved_parent) / PurePosixPath(given).name)
    return [given] if resolved == given else [given, resolved]


def run_writes(places: GitPlaces) -> list[str]:
    """The paths a contained run may write.

    Its worktree and git folder, the objects, and its branch's ref, lock and log.
    """
    writes = [places.worktree, places.admin, f"{places.common}/objects"]
    if places.branch:
        head = f"{places.common}/refs/heads/{places.branch}"
        writes += [head, f"{head}.lock", f"{places.common}/logs/refs/heads/{places.branch}"]
    return writes


def kept_writes(kept: Sequence[str], main: str | None) -> list[str]:
    """What a run in a board tree may not write beside the paths it denies by name.

    In a clone, the main repository's git folder `main` whole, then the `kept` files the board's
    git reads outside the sandbox; in a worktree, `kept` alone.
    """
    return [*([main] if bool(main) else []), *kept]


def checkout_denials(
    tree: str, names: Sequence[str], *, is_checkout: bool, clones: str | None
) -> list[str]:
    """What a sandbox whose tree is a checkout of its own may not write.

    The board reads it outside any sandbox: its config, its trees (`names`, relative to the tree)
    and its record of its clones. Nothing for any other tree: srt's deny outranks its allow, and a
    run's own tree is in the board's worktrees.
    """
    if not is_checkout:
        return []
    return [
        *(str(PurePosixPath(tree) / name) for name in names),
        *([clones] if bool(clones) else []),
    ]


def allowed_domains(configured: object) -> list[str]:
    """The hosts the worktree setup may reach: the repository's, host names only, else registries.

    No run or check reaches them.
    """
    if isinstance(configured, list) and all(isinstance(entry, str) for entry in configured):
        return [entry for entry in configured if _host_name(entry)]
    return list(SANDBOX_DOMAINS)


def _host_name(entry: str) -> bool:
    found = _HOST_NAME.fullmatch(entry)
    return found is not None and str(found.group(1)).lower() != "localhost"


def host_port(entry: str) -> bool:
    """Whether `entry` is `<host>:<port>`: srt admits every port of a host named without one."""
    host, separator, port = entry.rpartition(":")
    return (
        bool(separator)
        and bool(host)
        and host != "*"
        and "/" not in host
        and " " not in host
        and port.isascii()
        and port.isdigit()
        and 0 < int(port) <= _PORT
    )


def model_host(connection: ConnectionDefinition) -> str:
    """The `host:port` of a connection's address, the one host a contained run on it may reach."""
    where = address(connection)
    port = where.port or ("443" if where.scheme == "https" else "80")
    return f"{where.host}:{port}"


def contained_line(program: str, settings: str, line: str) -> list[str]:
    """The words that start the shell line `line` inside srt with the settings file `settings`.

    srt joins separate words unquoted, so the command goes as one line.
    """
    return [program, "--settings", settings, "-c", line]


def contained(program: str, settings: str, command: Sequence[str]) -> list[str]:
    """`command` started inside srt.

    srt's `NO_PROXY` leaves out this machine, where the sandbox refuses a direct connection, so it
    is unset and a model on this machine is reached through srt's proxy.
    """
    words = " ".join(shlex.quote(word) for word in command)
    return contained_line(program, settings, f"env -u NO_PROXY -u no_proxy {words}")


def _author_parts(author: str) -> tuple[str, str] | None:
    name, opened, rest = author.strip().partition("<")
    email = rest.strip().removesuffix(">").strip() if rest.strip().endswith(">") else ""
    name = name.strip()
    if opened and name and "@" in email and "<" not in email and ">" not in email:
        return name, email
    return None


def agent_identity(author: str | None) -> dict[str, str]:
    """The variables that make every commit of a run carry the agent's identity, not the owner's.

    `author` is `[agents] git_author` (`Name <email>`), or the board's own when it is unset or not
    of that form. git takes them over any identity its configuration names.
    """
    name, email = _author_parts(author or "") or (AGENT_NAME, AGENT_EMAIL)
    return {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
    }


def codex_program_folder(
    home: str, state: str, program: str, canonical: Callable[[str], str]
) -> str | None:
    """The one folder a codex run reads of the folders every run is denied, for the codex `program`.

    `canonical` resolves every link. `None` when the program is in none of them. The standalone
    installer puts codex under `~/.codex`, so the folder holding the resolved program, which holds
    its sibling binaries, is read and the rest of `~/.codex` stays denied. The folder comes from the
    resolved program and nothing a run or a repository names. `BadRequestError` when the program
    is directly in `~/.codex`, which would open the login beside it, or in another denied folder.
    """
    resolved = PurePosixPath(canonical(program))
    codex = PurePosixPath(canonical(str(PurePosixPath(home) / CODEX_HOME)))
    denied = [PurePosixPath(canonical(path)) for path in (*secret_paths(home), state)]
    folder = next((path for path in denied if resolved.is_relative_to(path)), None)
    if folder is None:
        return None
    own = resolved.parent
    if own != folder and folder == codex:
        return str(own)
    raise BadRequestError(
        f"codex is installed at {resolved}, in {folder}, which a board run is denied; "
        f"a board run needs codex installed outside {folder}"
    )
