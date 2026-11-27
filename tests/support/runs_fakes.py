"""Fake ports of the runs service: each records its calls in one shared log, in order."""

import os
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

from code_factory.platform.errors import ConflictError, NotFoundError, UnavailableError
from code_factory.runs.models import Repair
from code_factory.runs.ports import (
    Claimed,
    Given,
    Launch,
    LaunchPlan,
    Limit,
    LogUsage,
    RunPorts,
    Settings,
    TicketFacts,
    Tree,
)


class Calls:
    """Every call any fake received, as `name:detail` text, in order."""

    def __init__(self) -> None:
        self.log: list[str] = []

    def add(self, text: str) -> None:
        self.log.append(text)


class FakeTickets:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls
        self.facts_by_id: dict[str, TicketFacts] = {}
        self.events: list[tuple[str, str, str, dict[str, object]]] = []

    async def facts(self, ticket_id: str) -> TicketFacts:
        if ticket_id not in self.facts_by_id:
            raise NotFoundError(f"no ticket {ticket_id}")
        return self.facts_by_id[ticket_id]

    async def record_event(
        self,
        ticket_id: str,
        kind: str,
        run_id: str,
        data: dict[str, object],
        at: datetime,  # noqa: ARG002
    ) -> None:
        key = (ticket_id, kind, run_id)
        if any(e[:3] == key for e in self.events):
            return
        self.calls.add(f"event:{kind}")
        self.events.append((*key, data))

    async def clear_branch(self, ticket_id: str) -> None:
        self.calls.add(f"clear_branch:{ticket_id}")


class FakeTeams:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls
        self.refusal: str | None = None
        self.agent = "writer"
        self.passed: tuple[str, ...] = ()
        self.attach_error: Exception | None = None
        self.ended_with: list[str | None] = []

    async def claim_for_run(self, ticket_id: str, stage: str, settings: Settings) -> Claimed:  # noqa: ARG002
        self.calls.add(f"claim:{ticket_id}:{stage}")
        if self.refusal is not None:
            raise ConflictError(self.refusal)
        return Claimed(agent=self.agent, passed_over=self.passed)

    async def beat_start(self, ticket_id: str, lease_id: int) -> bool:  # noqa: ARG002
        return True

    async def attach_run(
        self,
        ticket_id: str,
        run_id: str,
        *,
        lease_id: int | None = None,
    ) -> None:
        del ticket_id, run_id, lease_id
        self.calls.add("attach")
        if self.attach_error is not None:
            raise self.attach_error

    async def end_claim(
        self,
        ticket_id: str,
        run_id: str | None,
        *,
        lease_id: int | None = None,
    ) -> None:
        del ticket_id, lease_id
        self.calls.add("end_claim")
        self.ended_with.append(run_id)

    async def start_refusal(self, ticket_id: str, stage: str, settings: Settings) -> str | None:  # noqa: ARG002
        return self.refusal


class FakeTrees:
    def __init__(self, calls: Calls, root: Path) -> None:
        self.calls = calls
        self.root = root
        self.refusal = ""
        self.redirected = ""
        self.dirty = False
        self.same_content = False
        self.new_commits: list[str] = []
        self.heads = ["head0"]
        self.fail_start: Exception | None = None
        self.fail_attempt: int | None = None  # fail only this attempt; any when `None`
        self.head_error: Exception | None = None
        self.commits_error: Exception | None = None
        self.fetch_error: Exception | None = None
        self.redirection_error: Exception | None = None
        self.made = False  # whether `start` says it made the tree

    async def start(self, repository: str, ticket_id: str, attempt: int) -> Tree:  # noqa: ARG002
        self.calls.add("tree")
        if self.fail_start and self.fail_attempt in {None, attempt}:
            raise self.fail_start
        path = self.root / f"tree-{attempt}"
        path.mkdir(exist_ok=True)
        return Tree(
            name=f"{ticket_id.lower()}-{attempt}",
            path=path,
            branch=f"ticket/{ticket_id.lower()}",
            made=self.made,
        )

    async def head(self, tree: Tree) -> str:  # noqa: ARG002
        if self.head_error is not None:
            raise self.head_error
        return self.heads[0] if len(self.heads) == 1 else self.heads.pop(0)

    async def commits(self, repository: str, base: str, new: str) -> list[str]:  # noqa: ARG002
        if self.commits_error is not None:
            raise self.commits_error
        return list(self.new_commits)

    async def tree_id(self, repository: str, commit: str) -> str:  # noqa: ARG002
        return "same" if self.same_content else f"{commit}-tree"

    async def uncommitted(self, repository: str, tree: Tree) -> bool:  # noqa: ARG002
        return self.dirty

    async def fetch_back(self, repository: str, tree: Tree) -> str:  # noqa: ARG002
        self.calls.add("fetch_back")
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.refusal

    async def save(self, repository: str, ticket_id: str, tree: Tree) -> None:  # noqa: ARG002
        self.calls.add("save")

    async def remove(self, repository: str, tree: Tree) -> None:  # noqa: ARG002
        self.calls.add("remove_tree")

    async def redirection(self, repository: str, tree: Tree) -> str:  # noqa: ARG002
        if self.redirection_error is not None:
            raise self.redirection_error
        return self.redirected


class FakeAgents:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls
        self.given_value = Given(
            agent="writer", runtime="claude", model="m1", connection="c", fingerprint="f1"
        )
        self.changed_after_probe: Given | None = None
        self.argv: tuple[str, ...] = ("/bin/sleep", "30")
        self.script: str | None = None  # a shell script run through the real wrapper
        self.launch_error: Exception | None = None
        self.usage = LogUsage()
        self.limit: Limit | None = None
        self._probed = False
        self.plans: list[LaunchPlan] = []
        self.during_launch: Callable[[], Awaitable[None]] | None = None
        self.refusal: str | None = None

    async def given(self, agent: str, stage: str) -> Given:  # noqa: ARG002
        if self._probed and self.changed_after_probe is not None:
            return self.changed_after_probe
        return self.given_value

    async def probe(self, given: Given) -> None:  # noqa: ARG002
        self.calls.add("probe")
        self._probed = True

    def launch_refusal(self, given: Given) -> str | None:  # noqa: ARG002
        return self.refusal

    async def launch(self, plan: LaunchPlan) -> Launch:
        self.calls.add("launch")
        self.plans.append(plan)
        if self.during_launch is not None:
            await self.during_launch()
        if self.launch_error:
            raise self.launch_error
        argv = self.argv
        env = {"PATH": "/usr/bin:/bin"}
        if self.script is not None:
            wrapper = (sys.executable, "-m", "code_factory.runs.adapters.runner")
            argv = (*wrapper, str(plan.exit_file), "--", "/bin/sh", "-c", self.script)
            env["PYTHONPATH"] = os.pathsep.join(sys.path)
            env["CODE_FACTORY_RUNS_DIR"] = str(plan.exit_file.parent)
        return Launch(argv=argv, env=env, digest="d1d1d1d1d1d1")

    async def log_usage(self, log: Path) -> LogUsage:  # noqa: ARG002
        return self.usage

    def usage_limit(self, log_text: str) -> Limit | None:  # noqa: ARG002
        return self.limit


class FakeTokens:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls
        self.issued: list[tuple[str, int | None, str, str, int]] = []

    async def issue(
        self, run_id: str, ticket_id: str | None, stage: str, repository: str, lifetime_s: int
    ) -> str:
        self.calls.add("token")
        self.issued.append(
            (
                run_id,
                None if ticket_id is None else int(ticket_id.removeprefix("CF-")),
                stage,
                repository,
                lifetime_s,
            )
        )
        return "tok-secret"

    async def revoke(self, run_id: str) -> None:  # noqa: ARG002
        self.calls.add("revoke")


class FakeMemory:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    async def deliver(self, run_id: str, ticket: TicketFacts, stage: str) -> str:  # noqa: ARG002
        self.calls.add("memory")
        return "m3m3m3m3m3m3"


class FakeFlow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.error: Exception | None = None
        self.prepared: list[str] = []
        self.prepare_error: Exception | None = None
        self.verified: list[tuple[str, str]] = []
        self.verify_error: Exception | None = None
        self.reservations: list[tuple[str, Repair, str]] = []
        self.released: list[tuple[str, str]] = []

    async def prepare_build(self, ticket_id: str) -> bool:
        self.prepared.append(ticket_id)
        if self.prepare_error is not None:
            raise self.prepare_error
        return False

    async def verify_build(self, ticket_id: str, head: str) -> None:
        self.verified.append((ticket_id, head))
        if self.verify_error is not None:
            raise self.verify_error

    async def admit_repair(self, ticket_id: str, repair: Repair, run_id: str = "") -> None:
        if run_id:
            self.reservations.append((ticket_id, repair, run_id))

    async def release_repair(self, ticket_id: str, run_id: str) -> None:
        self.released.append((ticket_id, run_id))

    async def build_ended(self, ticket_id: str, head: str) -> None:
        self.calls.append(("build", ticket_id, head))
        if self.error is not None:
            raise self.error

    async def review_ended(self, ticket_id: str, run_id: str, head: str) -> None:
        self.calls.append(("review", ticket_id, run_id, head))
        if self.error is not None:
            raise self.error


class FakeConfig:
    def __init__(self) -> None:
        self.value = Settings()

    async def settings(self, repository: str) -> Settings:  # noqa: ARG002
        return self.value

    async def root(self, repository: str) -> Path:  # noqa: ARG002
        return Path("/repo/main")


class Fakes:
    """All the fakes, and the `RunPorts` over them."""

    def __init__(self, root: Path) -> None:
        self.calls = Calls()
        self.tickets = FakeTickets(self.calls)
        self.teams = FakeTeams(self.calls)
        self.trees = FakeTrees(self.calls, root)
        self.agents = FakeAgents(self.calls)
        self.tokens = FakeTokens(self.calls)
        self.memory = FakeMemory(self.calls)
        self.config = FakeConfig()
        self.flow = FakeFlow()

    @property
    def ports(self) -> RunPorts:
        return RunPorts(
            tickets=self.tickets,
            teams=self.teams,
            trees=self.trees,
            agents=self.agents,
            tokens=self.tokens,
            memory=self.memory,
            config=self.config,
            flow=self.flow,
        )


def refuse_with(error: Exception) -> Exception:
    """A launch error of the kind the agents adapter raises."""
    return error if isinstance(error, UnavailableError) else UnavailableError(str(error))
