"""Errors the settings module raises on purpose."""

from code_factory.platform.errors import UnavailableError


def unjudged_message(entries: tuple[str, ...]) -> str:
    """The sentence for a scan that ran out of time before it judged these mounts."""
    named = f" {', '.join(entries)}" if entries else ""
    return (
        f"could not judge container_mounts{named} in time; "
        "no run starts with this config until they can be judged"
    )


class ConfigUnjudgedError(UnavailableError):
    """A repository's config names mounts that could not be judged in time."""
