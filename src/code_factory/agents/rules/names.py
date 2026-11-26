"""What an agent or a connection may be called."""

import re

from code_factory.agents.models.constants import NAME_LIMIT
from code_factory.platform.errors import BadRequestError

# The same expression the tables' check constraints hold, anchored for PostgreSQL.
NAME_PATTERN = rf"^[A-Za-z0-9][A-Za-z0-9._-]{{0,{NAME_LIMIT - 1}}}$"
_NAME = re.compile(NAME_PATTERN)


def check_name(name: str) -> None:
    """Refuse a name that is not 1 to 40 letters, digits, `-`, `_` or `.`, starting alphanumeric."""
    if _NAME.fullmatch(name) is None:
        msg = (
            f"a name is 1 to {NAME_LIMIT} letters, digits, '-', '_' or '.', "
            "starting with a letter or digit"
        )
        raise BadRequestError(msg)
