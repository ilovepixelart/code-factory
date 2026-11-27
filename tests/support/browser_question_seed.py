"""Seed Inbox and reply-link browser tests in their disposable schema."""

import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app_lifespan import IDLE_MODULES
from code_factory.app import build_resources, build_services
from code_factory.delivery.models import PullReading
from code_factory.delivery.service import DeliveryService
from code_factory.memory.models import NewMemory
from code_factory.memory.service import MemoryService
from code_factory.platform.config import Settings
from code_factory.platform.runtime import running
from code_factory.push.service import PushService
from code_factory.runs.models import PermissionRequest
from code_factory.runs.repository.permissions import PermissionRepository
from code_factory.talk.models import Choice
from code_factory.talk.service import TalkService
from code_factory.talk.tables import QuestionRow
from database_guard import assert_test_database


async def main() -> None:
    assert_test_database(os.environ["CODE_FACTORY_DATABASE_URL"])
    schema = os.environ["CODE_FACTORY_DB_SCHEMA"]
    if re.fullmatch(r"e2e_[0-9a-f]{12}", schema) is None:
        raise SystemExit("expected a browser test schema")
    seed = json.loads(sys.argv[1])
    resources = build_resources(Settings(_env_file=None))
    async with running(resources):
        services = build_services(resources, IDLE_MODULES)
        uow = resources.uow
        if target := seed.get("webhook"):
            await services.get(PushService).set_target("webhook", target)
        if url := seed.get("failingPull"):
            await services.get(DeliveryService).record_reading(
                seed["ticket"], "sample", url, PullReading(state="open", ci="failed")
            )
        if question := seed.get("question"):
            choices = [Choice.model_validate(choice) for choice in question.pop("choices", [])]
            await services.get(TalkService).ask(
                seed["ticket"], choices=choices, by="browser-test", **question
            )
        if rewritten := seed.get("rewrite"):
            async with uow() as session:
                number = int(seed["ticket"].removeprefix("CF-"))
                query = select(QuestionRow).where(
                    QuestionRow.ticket_number == number, QuestionRow.text == rewritten["before"]
                )
                row = (await session.scalars(query)).one()
                row.text = rewritten["after"]
        if permission := seed.get("permission"):
            async with uow() as session:
                await PermissionRepository(session).add_request(
                    PermissionRequest(
                        repository="sample",
                        ticket_key=seed["ticket"],
                        tool="Bash",
                        requested_at=datetime.now(UTC),
                        **permission,
                    )
                )
        if proposal := seed.get("memoryProposal"):
            await services.get(MemoryService).propose(
                NewMemory(repository="sample", kind="rule", source="agent", **proposal),
                by="run:browser-test",
            )


if __name__ == "__main__":
    asyncio.run(main())
