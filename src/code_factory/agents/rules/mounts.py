"""The command line of the checks container.

Its mounts, the secrets they may never reach and the tag of its image.
"""

import hashlib
from collections.abc import Sequence
from pathlib import PurePosixPath

from code_factory.agents.models.constants import SECRET_FILES
from code_factory.platform.errors import BadRequestError

TAG_PREFIX = "code-factory-checks"
_SHAPE = (
    "expected <host folder>:<folder inside>, the host one absolute or under ~/, "
    "the inside one absolute"
)
_REACHES = "the host folder is, holds or is in the home folder or a secret folder"
_OWN = ("PATH=", "TMPDIR=")


def _volume(host: str, inside: str, mode: str) -> list[str]:
    held = next((text for text in (host, inside) if ":" in text), None)
    if held is not None:
        raise BadRequestError(f"the checks container cannot mount {held}, which holds ':'")
    return ["--volume", f"{host}:{inside}:{mode}"]


def in_container(  # noqa: PLR0913  # the facts of one container, named by the caller
    engine: str,
    image: str,
    tree: str,
    *,
    readonly: Sequence[str],
    mounts: Sequence[tuple[str, str]],
    variables: Sequence[str],
    command: str,
) -> list[str]:
    """The words that run `command` in a container of `image` started by `engine`.

    No network, the tree mounted writable at its own path, `readonly` folders read-only at theirs
    and each of `mounts` (host, inside) read-only inside, nothing else, the tree as the working
    folder and `variables` (`NAME=value`) as its environment. The image's own `PATH` finds its
    toolchain and its own `TMPDIR` is kept: the host's names a folder the container lacks.
    """
    words = [engine, "run", "--rm", "--network", "none", "--init", *_volume(tree, tree, "rw")]
    for folder in readonly:
        words += _volume(folder, folder, "ro")
    for host, inside in mounts:
        words += _volume(host, inside, "ro")
    words += ["--workdir", tree]
    for variable in variables:
        if not variable.startswith(_OWN):
            words += ["--env", variable]
    return [*words, image, "/bin/sh", "-c", command]


def _plain(path: str) -> bool:
    """An absolute path below the root whose every part is a name."""
    parts = path.split("/")
    return path.startswith("/") and len(path) > 1 and all(part not in {".", ".."} for part in parts)


def container_mount(entry: str, home: str) -> tuple[str, str]:
    """A `[checks] container_mounts` entry `<host>:<inside>` as the host folder and the inside one.

    `~/` is read as `home`; both are absolute, neither climbs with `..`, and the host folder never
    reaches a secret or the home folder. `BadRequestError` names what is expected.
    """
    host, separator, inside = entry.partition(":")
    if host.startswith("~/"):
        host = f"{home.rstrip('/')}/{host.removeprefix('~/')}"
    if not separator or ":" in inside or not _plain(host) or not _plain(inside):
        raise BadRequestError(f"{entry}: {_SHAPE}")
    if mount_reaches_secrets(host, home, []):
        raise BadRequestError(f"{entry}: {_REACHES}")
    return host, inside


def secret_paths(home: str) -> list[str]:
    """Every secret every run is denied as a path, `~/` read as `home`."""
    base = PurePosixPath(home)
    return [str(base / secret.removeprefix("~/")) for secret in SECRET_FILES]


def mount_reaches_secrets(host: str, home: str, resolved: Sequence[str]) -> bool:
    """Whether a checks container mount of `host` would reach the home folder whole or a secret.

    `resolved` are the folders the secrets' links lead to. The mount reaches one when it is one,
    holds one or is in one; the board asks again of the resolved folder with the resolved secrets,
    so a link on either side cannot lead a mount into a secret.
    """
    where = PurePosixPath(host)
    if PurePosixPath(home).is_relative_to(where):
        return True
    return any(
        where.is_relative_to(secret) or PurePosixPath(secret).is_relative_to(where)
        for secret in (*secret_paths(home), *resolved)
    )


def checks_image_tag(text: bytes) -> str:
    """The tag of the checks image built from a container file of `text`.

    The first 16 hex characters of its SHA-256, so an unchanged file is never rebuilt and a
    changed one is a new tag.
    """
    return f"{TAG_PREFIX}:{hashlib.sha256(text).hexdigest()[:16]}"
