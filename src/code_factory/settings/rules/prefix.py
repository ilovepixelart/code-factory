"""The settings with a default this module owns."""

from code_factory.settings.models.config import DEFAULT_PREFIX, RepositoryConfig


def ticket_prefix(config: RepositoryConfig) -> str:
    """`tickets.prefix` when set, else `CF`; the lenient reading already dropped an invalid one."""
    tickets = config.tickets
    if tickets is None or tickets.prefix is None:
        return DEFAULT_PREFIX
    return tickets.prefix
