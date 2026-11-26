"""The checks container's name and turn, and the lines that say it never started."""

from collections.abc import Sequence

_DAEMON = ("docker: Error response from daemon:", "docker: Cannot connect to the Docker daemon")
NAME_PREFIX = "code-factory-check-"
CONTAINER_WAIT = "gate: checks wait for a container's turn"


def container_name(check_id: int) -> str:
    """The name a check's container goes by, so a timeout can remove it."""
    return f"{NAME_PREFIX}{check_id}"


def named_container(argv: Sequence[str], name: str) -> list[str]:
    """`argv` with `--name <name>` right after `--rm`."""
    words = list(argv)
    if "--rm" not in words:
        msg = "a checks container command line carries --rm"
        raise ValueError(msg)
    at = words.index("--rm") + 1
    return [*words[:at], "--name", name, *words[at:]]


def docker_never_started(log: str) -> bool:
    """Whether the log holds an engine error and no `gate: <step> starts` line before its end."""
    daemon = False
    for raw in log.splitlines():
        line = raw.lstrip()
        if line.startswith("gate: ") and line.endswith(" starts"):
            return False
        daemon = daemon or line.startswith(_DAEMON)
    return daemon


def next_turn(queued: Sequence[int], running: int, slots: int) -> int | None:
    """The smallest queued id when fewer than `slots` (at least one) containers run."""
    if not queued or running >= max(slots, 1):
        return None
    return min(queued)
