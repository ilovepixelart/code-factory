"""Fakes of the delivery tests: a scripted gh, a settable clock and the neighbours it reads."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import override

from code_factory.delivery.adapters.gh import GhResult, GhRunner, guard
from code_factory.delivery.ports import Candidate, NewIssueTicket, Switches
from code_factory.stages.models import Hold

TIP = "a" * 40
URL = "https://github.com/o/r/pull/9"
START = datetime(2026, 11, 1, tzinfo=UTC)
AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class ScriptedGh(GhRunner):
    """Answers by argv prefix and keeps every call."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[str]] = []
        self.script: dict[tuple[str, ...], GhResult] = {}

    @override
    async def run(self, root: Path, argv: Sequence[str], stdin: bytes | None = None) -> GhResult:
        guard(argv)
        self.calls.append(list(argv))
        for size in range(len(argv), 0, -1):
            found = self.script.get(tuple(argv[:size]))
            if found is not None:
                return found
        return GhResult(ok=False, stdout="", stderr="not scripted")

    def answer(self, prefix: tuple[str, ...], data: object = "", *, ok: bool = True) -> None:
        text = data if isinstance(data, str) else json.dumps(data)
        self.script[prefix] = GhResult(ok=ok, stdout=text if ok else "", stderr="" if ok else text)


@dataclass
class Fakes:
    ticket: Candidate
    pushed: list[tuple[str, str]] = field(default_factory=list)
    commit_messages: list[str] = field(default_factory=list)
    checks_verdict: str = "passed"
    switches: Switches = field(default_factory=lambda: Switches(ship=True, merge_waits=False))
    created: list[NewIssueTicket] = field(default_factory=list)
    caught_up: list[str] = field(default_factory=list)
    local_tip: str = TIP
    queued: list[tuple[str, str]] = field(default_factory=list)
    behaviour_text: str = ""

    hold: Hold | None = None
    policy_checks: list[tuple[str, str]] = field(default_factory=list)

    async def automatic_hold(self, ticket_id: str, head: str) -> Hold | None:
        self.policy_checks.append((ticket_id, head))
        return self.hold

    async def candidates(self) -> list[Candidate]:
        return [self.ticket]

    async def get(self, ticket_id: str) -> Candidate:  # noqa: ARG002
        return self.ticket

    async def create(self, new: NewIssueTicket) -> str:
        self.created.append(new)
        return f"CF-{900 + len(self.created)}"

    async def behaviour(self, ticket_id: str) -> str:  # noqa: ARG002
        return self.behaviour_text

    async def record_pull(self, ticket_id: str, url: str, state: str) -> None:
        pass

    async def record_merged(self, ticket_id: str) -> None:
        pass

    async def default_branch(self, repository: str) -> str:  # noqa: ARG002
        return "main"

    async def tip(self, repository: str, branch: str) -> tuple[str, str]:  # noqa: ARG002
        return self.local_tip, ""

    async def holds_code(self, repository: str, base: str, tip: str) -> bool:  # noqa: ARG002
        return True

    async def push(self, repository: str, commit: str, branch: str) -> None:  # noqa: ARG002
        self.pushed.append((commit, branch))

    async def messages(self, repository: str, base: str, tip: str) -> list[str]:  # noqa: ARG002
        return self.commit_messages

    async def paths(self, repository: str, base: str, tip: str) -> list[str]:  # noqa: ARG002
        return ["src/x.py"]

    async def descends(self, repository: str, older: str, newer: str) -> bool:  # noqa: ARG002
        return True

    async def remote_url(self, repository: str) -> str | None:  # noqa: ARG002
        return "https://github.com/o/r.git"

    async def catch_up(self, repository: str) -> None:
        self.caught_up.append(repository)

    async def verdict(self, repository: str, ticket_id: str, head: str) -> str:  # noqa: ARG002
        return self.checks_verdict

    async def configured(self, repository: str) -> bool:  # noqa: ARG002
        return True

    async def queue(self, ticket_id: str, head: str) -> None:
        self.queued.append((ticket_id, head))


class Places:
    def __init__(self, fakes: Fakes) -> None:
        self._fakes = fakes

    async def names(self) -> list[str]:
        return ["sample"]

    async def root(self, repository: str) -> Path:  # noqa: ARG002
        return Path("/nonexistent")

    async def switches(self, repository: str) -> Switches:  # noqa: ARG002
        return self._fakes.switches


def pull_answer(head: str = TIP, state: str = "OPEN") -> dict[str, object]:
    return {
        "url": URL, "state": state, "headRefOid": head, "baseRefName": "main",
        "statusCheckRollup": [
            {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}
        ],
        "mergeStateStatus": "CLEAN",
    }  # fmt: skip
