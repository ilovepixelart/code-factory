"""The folders no run may read, and the checks container mounts held away from them."""

from collections.abc import Callable, Sequence
from pathlib import PurePosixPath

# Every secret a run is denied, `~/` read as the home folder.
SECRET_FILES = (
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.config/gh",
    "~/.docker/config.json",
    "~/.netrc",
    "~/.npmrc",
    "~/.pypirc",
    "~/.git-credentials",
    "~/.omp",
    "~/.local/share/opencode/auth.json",
    "~/.kube",
    "~/.azure",
    "~/.pi/agent",
    "~/.codex",
    "~/.claude",
    "~/.claude.json",
)
VALIDATION_HOME = PurePosixPath("/home")
# Folders where reaching a path can block or touch the network; no mount holds one.
AUTOMOUNT_ROOTS = tuple(PurePosixPath(root) for root in ("/net", "/Volumes", "/mnt", "/Network"))
Resolve = Callable[[PurePosixPath], PurePosixPath]


def _plain(path: PurePosixPath) -> bool:
    """Absolute, below the root, and no `..`."""
    return path.is_absolute() and len(path.parts) > 1 and ".." not in path.parts


def secret_paths(home: PurePosixPath) -> list[PurePosixPath]:
    """Every secret as a path, `~/` read as `home`."""
    return [home / secret.removeprefix("~/") for secret in SECRET_FILES]


class Unjudged(Exception):  # noqa: N818  # a state of the scan, not a fault
    """A scan ran out of time before it could resolve a path; `entries` are the mounts left."""

    def __init__(self, entries: tuple[str, ...] = ()) -> None:
        super().__init__(entries)
        self.entries = entries


def on_automount_root(path: PurePosixPath) -> bool:
    """Whether `path` is, or is below, a folder where reaching it can block or touch a network."""
    return any(_folded(collapsed(path)).is_relative_to(_folded(root)) for root in AUTOMOUNT_ROOTS)


def collapsed(path: PurePosixPath) -> PurePosixPath:
    """`path` with a doubled leading slash read as one: `//a` is `/a` to the kernel."""
    if path.parts[:1] == ("//",):
        return PurePosixPath("/", *path.parts[1:])
    return path


def _folded(path: PurePosixPath) -> PurePosixPath:
    return PurePosixPath(str(path).lower())


def _reaches(host: PurePosixPath, home: PurePosixPath, secrets: list[PurePosixPath]) -> bool:
    """Whether `host` is, holds or is inside `home` or a secret, names folded to lower case."""
    reached = _folded(host)
    return _folded(home).is_relative_to(reached) or any(
        reached.is_relative_to(secret) or secret.is_relative_to(reached)
        for secret in map(_folded, secrets)
    )


def mount_reaches_secrets(
    host: PurePosixPath, home: PurePosixPath, resolve: Resolve = collapsed
) -> bool:
    """Whether mounting `host` would reach the home folder whole or a secret.

    That is: `host` is, holds or is inside the home folder or a secret, as spelled and as it
    resolves. Names compare in lower case: a case-insensitive disk reaches `~/.ssh` as `~/.SSH`.
    `resolve` maps a path to the one it reaches on disk (links followed); the host, the home and
    each secret go through it, so a link into a secret, a link as the home or a secret that is a
    link compares by its target, and a folder holding a linked secret is still caught as spelled.
    """
    host = collapsed(host)
    secrets = secret_paths(home)
    return _reaches(host, home, secrets) or _reaches(
        resolve(host), resolve(home), [resolve(secret) for secret in secrets]
    )


def _host_under(host_text: str, home: PurePosixPath) -> PurePosixPath:
    """The host folder of a mount, `~/` read as `home`."""
    if host_text.startswith("~/"):
        return home / host_text.removeprefix("~/")
    return PurePosixPath(host_text)


def _elsewhere_in_home(host_text: str, real_homes: Sequence[PurePosixPath]) -> bool:
    """Whether the host is a folder of `/home` that is in none of the real homes.

    Only those are walked on disk, and `/home` can be an automount map that must not be probed.
    """
    host = _folded(collapsed(PurePosixPath(host_text)))
    home = _folded(VALIDATION_HOME)
    return host.is_relative_to(home) and not any(
        host.is_relative_to(_folded(real)) for real in real_homes if real != VALIDATION_HOME
    )


def container_mount_problem(
    entry: str, homes: Sequence[PurePosixPath] = (VALIDATION_HOME,), resolve: Resolve = collapsed
) -> str | None:
    """Why `entry` is no `<host>:<inside>` mount of a checks container, or None when it is one.

    The host folder must reach no secret of any of `homes`: the synthetic home every check shares
    and, on a machine, its real one, so an absolute spelling of the home is held like `~/`.
    `resolve` is `mount_reaches_secrets`'s.
    """
    host_text, separator, inside_text = entry.partition(":")
    inside = PurePosixPath(inside_text)
    hosts = [(_host_under(host_text, home), home) for home in homes]
    if not separator or ":" in inside_text or not (_plain(hosts[0][0]) and _plain(inside)):
        return (
            f"{entry}: expected <host folder>:<folder inside>, the host one absolute or under ~/, "
            "the inside one absolute"
        )
    if any(ord(char) < ord(" ") or char == "\x7f" for char in host_text):
        return f"{entry}: the host folder holds a control character"
    if any(on_automount_root(host) for host, _ in hosts):
        return f"{entry}: the host folder is on a network or automounted volume"
    if any(mount_reaches_secrets(host, home, resolve) for host, home in hosts):
        return f"{entry}: the host folder is, holds or is in the home folder or a secret folder"
    if not host_text.startswith("~/") and _elsewhere_in_home(host_text, homes[1:]):
        return f"{entry}: the host folder is in {VALIDATION_HOME} but not in the home folder"
    return None
