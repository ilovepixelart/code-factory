"""The Build preflight over a fake verifier and real owner state files."""

import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from code_factory.checks.adapters.logs import LogFiles
from code_factory.checks.adapters.spec import publish_receipt
from code_factory.checks.adapters.workspace import Workspaces
from code_factory.checks.models import Scope
from code_factory.checks.service import CheckService, spec
from code_factory.git.service import GitService
from code_factory.platform.contained import ContainedRunner, Work
from code_factory.platform.errors import ConflictError, UnavailableError

TICKET = "CF-1"
HEAD = "a" * 40
FILE = "acceptance.spec"
PROOF = {"commit": HEAD, "nodes": [], "files": {FILE: "d" * 64}}


class Verifier:
    def __init__(self, state: Path) -> None:
        self.state = state
        self.request = state / "spec-lock-requests" / f"{TICKET}.json"
        self.receipt = state / "spec-locks" / f"{TICKET}.json"
        self.calls: list[tuple[str, str, bool]] = []
        self.code: int | None = 0
        self.can_finish: asyncio.Event | None = None
        self.stdout = json.dumps(PROOF)
        self.config = SimpleNamespace(sandboxed=True, commands={Scope.REACHED: "check"})
        self.changed_files = AsyncMock(return_value=[])
        self.tree = state / "snapshot"
        self.judge = AsyncMock(return_value=SimpleNamespace(head=HEAD, tracked_clean=True))
        self.request.parent.mkdir(parents=True)
        self.request.write_text(json.dumps({"argv": ["/owner/bin/check-spec", "with space"]}))

    @asynccontextmanager
    async def snapshot(
        self,
        repository: str,
        commit: str,
        subject: str,
        setup: object,
        *,
        use_cache: bool,
    ) -> AsyncGenerator[SimpleNamespace]:
        assert (repository, commit, subject, setup) == ("repo", HEAD, TICKET, None)
        assert not use_cache
        yield SimpleNamespace(path=self.tree, git_dir=self.tree / ".git")

    async def run(  # records the same args as the runner
        self,
        work: Work,
        repository: str,
        command: str,
        tree: Path,
        log: Path,
        limit_s: int,
        *,
        require_sandbox: bool,
    ) -> int | None:
        assert work is Work.CHECKS
        assert tree == self.tree
        assert limit_s == 240
        self.calls.append((repository, command, require_sandbox))
        if self.can_finish is not None:
            await self.can_finish.wait()
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(self.stdout)
        return self.code


@pytest.fixture
def preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[CheckService, Verifier]:
    verifier = Verifier(tmp_path)
    service = object.__new__(CheckService)
    git = object.__new__(GitService)
    monkeypatch.setattr(git, "changed_files", verifier.changed_files)
    monkeypatch.setattr(git, "branch_state", AsyncMock(return_value=SimpleNamespace(tip=HEAD)))
    ports = {
        "_spec_state": tmp_path,
        "_slots": asyncio.Semaphore(1),
        "_group": None,
        "_draining": False,
        "_admission_limit": 1,
        "_spec_tasks": {},
        "_spec_failures": {},
        "_deps": SimpleNamespace(git=git),
        "_ticket": AsyncMock(
            return_value=SimpleNamespace(id=TICKET, repository="repo", branch="ticket/cf-1")
        ),
        "_config": AsyncMock(return_value=verifier.config),
        "_policy": SimpleNamespace(
            places=tuple,
            refresh=AsyncMock(),
        ),
        "_workspaces": SimpleNamespace(snapshot=verifier.snapshot),
        "_runner": verifier,
        "_judge_tree": SimpleNamespace(read=verifier.judge),
        "_logs": LogFiles(tmp_path),
    }
    for name, fake in ports.items():
        monkeypatch.setattr(service, name, fake, raising=False)
    monkeypatch.setattr(spec, "find_program", AsyncMock(return_value=Path("/owner/bin/check-spec")))
    monkeypatch.setattr(spec, "base_environment", AsyncMock(return_value={}))
    return service, verifier


async def test_preflight_publishes_one_receipt_and_reuses_it_on_retry(
    preflight: tuple[CheckService, Verifier],
) -> None:
    service, verifier = preflight
    verifier.stdout = f"runtime loaded\n{verifier.stdout}\nnormal shutdown"

    await service.prepare_build(TICKET)
    await service.verify_build(TICKET, HEAD)
    await service.prepare_build(TICKET)

    found = json.loads(verifier.receipt.read_text())
    assert found == {
        **PROOF,
        "request_sha256": hashlib.sha256(verifier.request.read_bytes()).hexdigest(),
    }
    assert verifier.calls == [
        ("repo", "TMPDIR=\"$XDG_RUNTIME_DIR\" /owner/bin/check-spec 'with space'", True)
    ]


@pytest.mark.parametrize(
    ("output", "code", "reason"),
    [
        ("", 1, "expected-failure checks for CF-1 did not pass"),
        ("", None, "expected-failure checks for CF-1 did not pass"),
        ("not a receipt", 0, "did not return a receipt"),
        (json.dumps({**PROOF, "commit": "b" * 40}), 0, "does not describe the committed snapshot"),
    ],
)
async def test_failed_or_mismatched_proofs_cannot_publish_a_receipt(
    preflight: tuple[CheckService, Verifier],
    output: str,
    code: int | None,
    reason: str,
) -> None:
    service, verifier = preflight
    verifier.stdout = output
    verifier.code = code

    with pytest.raises(ConflictError, match=reason):
        await service.prepare_build(TICKET)

    assert not verifier.receipt.exists()


async def test_a_successful_verifier_that_changed_a_tracked_file_still_refuses_build(
    preflight: tuple[CheckService, Verifier],
) -> None:
    service, verifier = preflight
    verifier.judge.side_effect = [
        SimpleNamespace(head=HEAD, tracked_clean=True),
        SimpleNamespace(head=HEAD, tracked_clean=False),
    ]

    with pytest.raises(ConflictError, match="committed spec for CF-1 changed"):
        await service.prepare_build(TICKET)

    assert not verifier.receipt.exists()


async def test_existing_receipt_cannot_silently_accept_a_new_request(
    preflight: tuple[CheckService, Verifier],
) -> None:
    service, verifier = preflight
    await service.prepare_build(TICKET)
    saved = verifier.receipt.read_bytes()
    verifier.request.write_text(json.dumps({"argv": ["/owner/bin/check-spec", "different"]}))

    with pytest.raises(ConflictError, match="request for CF-1 changed"):
        await service.verify_build(TICKET, HEAD)

    assert verifier.receipt.read_bytes() == saved


async def test_existing_receipt_is_revalidated_against_the_actual_build_head(
    preflight: tuple[CheckService, Verifier],
) -> None:
    service, verifier = preflight
    await service.prepare_build(TICKET)
    verifier.changed_files.return_value = [FILE]
    actual = "b" * 40

    with pytest.raises(ConflictError, match="Restore the sealed files"):
        await service.verify_build(TICKET, actual)

    verifier.changed_files.assert_awaited_with("repo", HEAD, actual, [FILE])


async def test_an_unsandboxed_repository_never_runs_the_verifier(
    preflight: tuple[CheckService, Verifier],
) -> None:
    service, verifier = preflight
    verifier.config.sandboxed = False

    with pytest.raises(ConflictError, match="require the agent sandbox"):
        await service.prepare_build(TICKET)

    assert verifier.calls == []
    assert not verifier.receipt.exists()


async def test_a_spec_request_needs_a_required_merge_check(
    preflight: tuple[CheckService, Verifier],
) -> None:
    service, verifier = preflight
    verifier.config.commands[Scope.REACHED] = None

    with pytest.raises(ConflictError, match="enforce the receipt at merge"):
        await service.prepare_build(TICKET)

    assert verifier.calls == []


@pytest.mark.parametrize(
    "request_text", ["{}", '{"argv": []}', '{"argv": ["/bin/verify", 2]}', '{"argv": ["verify"]}']
)
async def test_invalid_requests_refuse_build_without_executing(
    preflight: tuple[CheckService, Verifier],
    request_text: str,
) -> None:
    service, verifier = preflight
    verifier.request.write_text(request_text)

    with pytest.raises(ConflictError, match=r"the spec (request|verifier)"):
        await service.prepare_build(TICKET)

    assert verifier.calls == []
    assert not verifier.receipt.exists()


async def test_a_symlink_request_does_not_select_a_verifier(
    preflight: tuple[CheckService, Verifier],
    tmp_path: Path,
) -> None:
    service, verifier = preflight
    elsewhere = tmp_path / "other.json"
    verifier.request.rename(elsewhere)
    verifier.request.symlink_to(elsewhere)

    with pytest.raises(ConflictError, match="spec request for CF-1 cannot be read"):
        await service.prepare_build(TICKET)

    assert verifier.calls == []


async def test_a_request_cannot_supply_an_untrusted_verifier(
    preflight: tuple[CheckService, Verifier],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, verifier = preflight
    monkeypatch.setattr(spec, "find_program", AsyncMock(return_value=None))

    with pytest.raises(ConflictError, match="install the spec verifier outside"):
        await service.prepare_build(TICKET)

    assert verifier.calls == []


async def test_no_receipt_means_a_new_request_cannot_race_into_an_existing_build(
    preflight: tuple[CheckService, Verifier],
) -> None:
    service, verifier = preflight

    with pytest.raises(ConflictError, match="receipt for CF-1 is missing"):
        await service.verify_build(TICKET, HEAD)

    assert verifier.calls == []


async def test_an_uncommitted_snapshot_is_refused_before_any_check_runs(
    preflight: tuple[CheckService, Verifier],
) -> None:
    service, verifier = preflight
    verifier.judge.return_value = SimpleNamespace(head=HEAD, tracked_clean=False)

    with pytest.raises(ConflictError, match="snapshot for CF-1 no longer matches"):
        await service.prepare_build(TICKET)

    assert verifier.calls == []


async def test_a_receipt_write_failure_never_licenses_build(
    preflight: tuple[CheckService, Verifier],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, verifier = preflight
    monkeypatch.setattr(spec, "publish_receipt", AsyncMock(side_effect=OSError))

    with pytest.raises(UnavailableError, match="receipt for CF-1 could not be written"):
        await service.prepare_build(TICKET)

    assert not verifier.receipt.exists()


async def test_no_request_leaves_build_unaffected(
    preflight: tuple[CheckService, Verifier],
) -> None:
    service, verifier = preflight
    verifier.request.unlink()

    await service.prepare_build(TICKET)
    await service.verify_build(TICKET, HEAD)

    assert verifier.calls == []
    assert not verifier.receipt.exists()


async def test_server_preflight_returns_pending_deduplicates_tasks_and_reuses_the_proof(
    preflight: tuple[CheckService, Verifier],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, verifier = preflight
    verifier.can_finish = asyncio.Event()
    async with asyncio.TaskGroup() as group:
        monkeypatch.setattr(service, "_group", group)
        for _ in range(2):
            with pytest.raises(ConflictError, match="checks for CF-1 are running"):
                await service.prepare_build(TICKET)
        assert not verifier.receipt.exists()
        verifier.can_finish.set()

    assert len(verifier.calls) == 1
    assert await service.prepare_build(TICKET) is False
    await service.verify_build(TICKET, HEAD)


async def test_failed_background_proof_is_reported_without_running_it_again_on_every_poll(
    preflight: tuple[CheckService, Verifier],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, verifier = preflight
    verifier.code = 1
    async with asyncio.TaskGroup() as group:
        monkeypatch.setattr(service, "_group", group)
        with pytest.raises(ConflictError, match="checks for CF-1 are running"):
            await service.prepare_build(TICKET)

    with pytest.raises(ConflictError, match="checks for CF-1 did not pass"):
        await service.prepare_build(TICKET)

    assert len(verifier.calls) == 1


async def test_an_isolated_spec_snapshot_does_not_take_the_tickets_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tree = tmp_path / "snapshot"
    tree.mkdir()
    (tree / ".git").write_text(f"gitdir: {tmp_path / 'worktrees' / tree.name}\n")
    git = object.__new__(GitService)
    remove = AsyncMock()
    monkeypatch.setattr(git, "add_snapshot", AsyncMock(return_value=tree))
    monkeypatch.setattr(git, "remove_snapshot", remove)
    workspace = Workspaces(git, object.__new__(ContainedRunner), tmp_path / "state")
    cache = AsyncMock()
    monkeypatch.setattr(workspace, "_cache", cache)

    async with workspace.snapshot("repo", HEAD, TICKET, None, use_cache=False) as result:
        assert result.path == tree

    cache.assert_not_awaited()
    remove.assert_awaited_once_with("repo", tree)


async def test_concurrent_publishers_keep_one_complete_receipt(tmp_path: Path) -> None:
    await asyncio.gather(
        publish_receipt(tmp_path, f"{TICKET}.json", "first proof"),
        publish_receipt(tmp_path, f"{TICKET}.json", "second proof"),
    )
    (receipt,) = list((tmp_path / "spec-locks").iterdir())
    assert receipt.read_text() in {"first proof", "second proof"}
