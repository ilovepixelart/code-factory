"""`code-factory sample-prepare`, `sample-load NAME` and `sample-drop`.

They work in the schema named by `CODE_FACTORY_DB_SCHEMA`.
"""

import argparse
import asyncio

from code_factory.platform.config import load_settings
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.sample import service
from code_factory.sample.service import SampleService


def _prepare(_args: argparse.Namespace) -> int:
    asyncio.run(service.prepare(load_settings()))
    return 0


def _drop(_args: argparse.Namespace) -> int:
    asyncio.run(service.drop(load_settings()))
    return 0


async def _load(args: argparse.Namespace, services: Services) -> int:
    await services.get(SampleService).load(args.name)
    return 0


def _name(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", help="the sample to load")


commands = (
    Command("sample-prepare", "create and migrate the schema of a sample", run=_prepare),
    Command(
        "sample-load",
        "load a named sample into the prepared schema",
        configure=_name,
        run_async=_load,
        check=service.check_target,
    ),
    Command("sample-drop", "drop the schema of a sample", run=_drop),
)
