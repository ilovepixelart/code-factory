"""Import a real completed-result receipt through the owner-facing command."""

import argparse
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from code_factory.evals.cli import eval_command
from code_factory.platform.errors import BadRequestError
from code_factory.repositories.service import RepositoryService


async def test_record_command_supplies_attributable_spend_to_factory(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    services = app.state.services
    project = tmp_path / "receipt-project"
    project.mkdir()
    await services.get(RepositoryService).track(project)
    path = tmp_path / "completed.json"
    result = {
        "receipt": "ci/2026-11-20/7923",
        "recorded_at": "2026-11-20T12:00:00Z",
        "kind": "build",
        "setup": {"stage": "build", "runtime": "codex", "model": "model-from-the-driver"},
        "runs": 1,
        "pass_at_1": 1.0,
        "pass_k": 1.0,
        "pass_at_k": 1.0,
    }
    parser = argparse.ArgumentParser()
    eval_command.configure(parser)
    args = parser.parse_args(
        ["record", "smoke", "--repository", project.name, "--input", str(path)]
    )
    assert eval_command.run_async is not None

    path.write_text(json.dumps(result))
    assert await eval_command.run_async(args, services) == 0
    first_output = capsys.readouterr().out
    assert await eval_command.run_async(args, services) == 0
    assert capsys.readouterr().out == first_output
    endpoint = "/api/factory/dashboard?from=2026-11-20&to=2026-11-21"
    response = await client.get(endpoint)
    assert response.status_code == 200
    assert response.json()["cost"]["measurement"] is None

    path.write_text(json.dumps({**result, "receipt": "ci/2026-11-20/7924", "cost": 2.5}))
    assert await eval_command.run_async(args, services) == 0
    response = await client.get(endpoint)
    assert response.status_code == 200
    assert response.json()["cost"]["measurement"] == 2.5

    path.write_text(json.dumps({**result, "recorded_at": "2026-11-20T12:00:00"}))
    with pytest.raises(BadRequestError, match="timezone"):
        await eval_command.run_async(args, services)
