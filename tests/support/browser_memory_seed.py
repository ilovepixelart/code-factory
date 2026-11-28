"""Seed dated entries for Memory review tests in their disposable PostgreSQL schema."""

import asyncio
import json
import os
import re
import sys
from datetime import UTC, date, datetime, time

from code_factory.app import build_resources
from code_factory.memory.models import MemoryEdit, NewMemory
from code_factory.memory.service import MemoryService
from code_factory.platform.config import Settings
from code_factory.platform.runtime import running
from database_guard import assert_test_database


async def main() -> None:
    assert_test_database(os.environ["CODE_FACTORY_DATABASE_URL"])
    if re.fullmatch(r"e2e_[0-9a-f]{12}", os.environ["CODE_FACTORY_DB_SCHEMA"]) is None:
        raise SystemExit("expected a browser test schema")

    entries = json.loads(sys.argv[1])
    resources = build_resources(Settings(_env_file=None))
    ids: list[str] = []
    async with running(resources):
        for fields in entries:
            moment = datetime.combine(date.fromisoformat(fields.pop("day")), time.min, UTC)
            memory = MemoryService(resources.uow, clock=lambda at=moment: at)
            saved = await memory.add(NewMemory(repository="sample", **fields), by="browser-test")
            await memory.edit("sample", saved.id, MemoryEdit())
            ids.append(saved.id)
    sys.stdout.write(json.dumps(ids))


if __name__ == "__main__":
    asyncio.run(main())
