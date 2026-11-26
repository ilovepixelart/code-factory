"""The keeper's pass: one repository that cannot be judged never stops the others."""

import pytest

from code_factory.checks.service import CheckService
from code_factory.settings.models.errors import ConfigUnjudgedError


async def test_a_repository_whose_config_cannot_be_judged_does_not_end_the_pass(
    checks: CheckService, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified: list[str] = []

    async def unjudged(repository: str) -> str | None:
        raise ConfigUnjudgedError(repository)

    async def due_verify(repository: str) -> None:
        verified.append(repository)

    monkeypatch.setattr(checks, "due_main", unjudged)
    monkeypatch.setattr(checks, "due_verify", due_verify)
    await checks.tick()
    assert verified == ["sample"]
