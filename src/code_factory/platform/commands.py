"""How a CLI command that takes `run(args)` reaches the modules' services.

`cli` stores the services opener in the parsed arguments; a command that needs services calls
`command_services(args)` inside its own event loop. A `run_async` command is already given them.
"""

import argparse
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from code_factory.platform.config import Settings, load_settings
from code_factory.platform.services import Services

OPENER_ARGUMENT = "services_opener"  # not a user option: `_add` in cli sets it as a default


class OpenServices(Protocol):
    """Builds every module's services on the started runtime (see `app.open_services`)."""

    def __call__(
        self, settings: Settings, *, database: bool = True
    ) -> AbstractAsyncContextManager[Services]:
        """Open them; `database=False` builds them without a database behind them."""


def command_services(
    args: argparse.Namespace, *, database: bool = True
) -> AbstractAsyncContextManager[Services]:
    """The services, for `async with` in a command's own loop.

    With the database (the default) the schema is checked first, as for `run_async`. With
    `database=False` neither `CODE_FACTORY_DATABASE_URL` nor a database is needed (`install` and
    `init` run on a fresh machine) and a service that uses the database raises a sentence saying
    the command runs without one.
    """
    opener: OpenServices = getattr(args, OPENER_ARGUMENT)
    return opener(load_settings(database=database), database=database)
