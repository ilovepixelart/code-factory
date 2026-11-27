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

RESULT = {
    "receipt": "ci/2026-11-20/7923",
    "recorded_at": "2026-11-20T12:00:00Z",
    "kind": "build",
    "setup": {"stage": "build", "runtime": "codex", "model": "model-from-the-driver"},
    "runs": 1,
    "pass_at_1": 1.0,
    "pass_k": 1.0,
    "pass_at_k": 1.0,
}


async def test_record_command_supplies_attributable_spend_to_factory(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    services = app.state.services
    project = tmp_path / "receipt-project"
    project.mkdir()
    await services.get(RepositoryService).track(project)
    path = tmp_path / "completed.json"
    parser = argparse.ArgumentParser()
    eval_command.configure(parser)
    args = parser.parse_args(
        ["record", "smoke", "--repository", project.name, "--input", str(path)]
    )
    assert eval_command.run_async is not None

    path.write_text(json.dumps(RESULT))
    assert await eval_command.run_async(args, services) == 0
    first_output = capsys.readouterr().out
    assert await eval_command.run_async(args, services) == 0
    assert capsys.readouterr().out == first_output
    endpoint = "/api/factory/dashboard?from=2026-11-20&to=2026-11-21"
    response = await client.get(endpoint)
    assert response.status_code == 200
    assert response.json()["cost"]["measurement"] is None

    path.write_text(json.dumps({**RESULT, "receipt": "ci/2026-11-20/7924", "cost": 2.5}))
    assert await eval_command.run_async(args, services) == 0
    response = await client.get(endpoint)
    assert response.status_code == 200
    assert response.json()["cost"]["measurement"] == 2.5

    path.write_text(json.dumps({**RESULT, "recorded_at": "2026-11-20T12:00:00"}))
    with pytest.raises(BadRequestError, match="timezone"):
        await eval_command.run_async(args, services)


async def test_record_rejects_unsupported_arguments_and_invalid_receipts(
    app: FastAPI, tmp_path: Path
) -> None:
    services = app.state.services
    project = tmp_path / "invalid-receipts"
    project.mkdir()
    await services.get(RepositoryService).track(project)
    path = tmp_path / "receipt.json"
    parser = argparse.ArgumentParser()
    eval_command.configure(parser)
    assert eval_command.run_async is not None

    no_input = parser.parse_args(["record", "smoke"])
    report_with_input = parser.parse_args(["report", "smoke", "--input", str(path)])
    with pytest.raises(BadRequestError, match="record needs --input"):
        await eval_command.run_async(no_input, services)
    with pytest.raises(BadRequestError, match="--input is for eval record"):
        await eval_command.run_async(report_with_input, services)

    params = parser.parse_args(
        ["record", "smoke", "--repository", project.name, "--input", str(path)]
    )
    with pytest.raises(BadRequestError, match="could not read the evaluation receipt"):
        await eval_command.run_async(params, services)

    for content, reason in (
        ("[broken", "valid UTF-8 JSON"),
        ("[]", "must be a JSON object"),
        ('{"recorded_at": "2026-11-20T12:00:00Z"}', "source receipt ID"),
        (json.dumps({**RESULT, "recorded_at": "2200-01-01T00:00:00Z"}), "after the current time"),
        (json.dumps({**RESULT, "pass_at_1": None}), "must supply all metrics"),
        (json.dumps({**RESULT, "setup": {"stage": "deploy"}}), "setup stage must be"),
        (json.dumps({**RESULT, "setup": {}}), "must identify the setup"),
    ):
        path.write_text(content)
        with pytest.raises(BadRequestError, match=reason):
            await eval_command.run_async(params, services)
