"""The environment a check or a verification starts with."""

import os
from collections.abc import Sequence
from pathlib import Path

from code_factory.platform.contained import BASE_VARIABLES, EMPTY_PATH
from code_factory.platform.programs import find_path


async def base_environment(places: Sequence[Path]) -> dict[str, str]:
    """The base variables and a `PATH` cut to the folders a run cannot have written."""
    path = await find_path(places) or EMPTY_PATH
    return {
        **{name: os.environ[name] for name in BASE_VARIABLES if name in os.environ},
        "PATH": path,
    }
