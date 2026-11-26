"""The Team page's read: every port answered together, then assembled."""

import asyncio
import logging
from collections.abc import Awaitable

from code_factory.platform.errors import UnavailableError
from code_factory.team import rules
from code_factory.team.models import Facts, TeamNow, Worker
from code_factory.team.service.base import DAY, PORT_TIMEOUT, ServiceBase, fan_out, together

logger = logging.getLogger(__name__)
COMMITS_BEFORE_CYCLE = 30 * DAY


class Page(ServiceBase):
    """`GET /api/team/now`: what needs the owner, waits, works, merged today, stale."""

    @staticmethod
    async def _page_read[T](name: str, call: Awaitable[T]) -> T:
        """A port read for the page: any failure is one sentence naming the port."""
        try:
            async with asyncio.timeout(PORT_TIMEOUT):
                return await call
        except Exception:
            logger.exception("the team page could not read %s", name)
            raise UnavailableError(f"the team page could not read {name}") from None

    async def _first_commits(
        self, repositories: list[tuple[str, str]], since: float
    ) -> dict[str, dict[str, float]]:
        """Each repository's first commits by ticket id; none without git."""
        if self._git is None:
            return {}
        git = self._git
        logs = await fan_out([git.first_commit_log(path, since) for _name, path in repositories])
        return {
            name: rules.first_commits(log)
            for (name, _path), log in zip(repositories, logs, strict=True)
        }

    async def _tags(self, paths: list[str]) -> list[tuple[str, float]]:
        if self._git is None:
            return []
        found = await fan_out([self._git.tags(path) for path in paths])
        return [tag for tags in found for tag in tags]

    async def now(self, now: float | None = None) -> TeamNow:
        """The Team page at `now`: its ports are read together, a failed one fails the page."""
        at = self._seconds(now)
        ports = self._ports()
        read = self._page_read
        async with together() as group:
            defined = group.create_task(read("the agents", ports.agents.team_agents()))
            repos = group.create_task(read("the repositories", ports.tickets.repositories()))
            active = group.create_task(read("the runs", ports.runs.active_runs()))
            gates = group.create_task(read("the gates", ports.gates.running_gates()))
            owner = group.create_task(read("the inbox", ports.owner.owner_items()))
            sessions = group.create_task(read("the sessions", ports.sessions.subagents_at_work()))
            jobs = group.create_task(read("the jobs", ports.jobs.running_land_jobs()))
        agents = defined.result()
        repositories = repos.result()
        cycle = rules.cycle_since(at, await self._tags([r.path for r in repositories]))
        today = at // DAY * DAY
        pairs = [(r.name, r.path) for r in repositories]
        async with together() as group:
            gathered = group.create_task(
                read("the tickets", ports.tickets.team_facts(min(today, cycle.since)))
            )
            commits = group.create_task(
                self._first_commits(pairs, cycle.since - COMMITS_BEFORE_CYCLE)
            )
        firsts = commits.result()
        tickets = tuple(
            t.model_copy(
                update={"first_commit": firsts.get(t.reference.repository, {}).get(t.reference.id)}
            )
            for t in gathered.result()
        )
        repository_of = {t.reference.id: t.reference.repository for t in tickets}
        workers: list[Worker] = [rules.gate_worker(g) for g in gates.result()]
        workers += [w for w in (rules.ship_worker(t, at) for t in tickets) if w is not None]
        workers += [rules.run_worker(a, at) for a in active.result()]
        workers += [
            rules.land_worker(j, repository_of.get(j.ticket_id, ""), at) for j in jobs.result()
        ]
        workers += [
            rules.session_worker(s, repository_of.get(s.ticket_id, "")) for s in sessions.result()
        ]
        return rules.assemble(
            Facts(
                now=at,
                today=today,
                cycle=cycle,
                tickets=tickets,
                workers=tuple(workers),
                owner=tuple(owner.result()),
                agents=tuple(a.name for a in agents),
                paused=tuple(a.name for a in agents if a.paused_at is not None),
            )
        )
