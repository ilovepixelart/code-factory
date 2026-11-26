"""The Flow page: ledger rows, ticket facts, runs and branch cuts through the pure assembly."""

from code_factory.metrics.models import FlowPage, MergeFact, TicketFlow, TrackedRepo
from code_factory.metrics.repository import MetricsRepository
from code_factory.metrics.rules.flow import InFlight, assemble_flow
from code_factory.metrics.rules.stages import range_of
from code_factory.metrics.service.deps import DAY, Deps, instant
from code_factory.platform.errors import UnavailableError

COST_LOOKBACK_S = 30 * DAY  # a merged ticket's runs may have started before the window
IN_FLIGHT_STAGES = {"build", "review"}


class WebAddresses:
    """Each repository's GitHub address, asked of git once and kept."""

    def __init__(self) -> None:
        self._known: dict[str, str | None] = {}

    async def of(self, deps: Deps, repo: TrackedRepo) -> str | None:
        """The address, or None when the repository has no GitHub origin."""
        if repo.name not in self._known:
            try:
                self._known[repo.name] = await deps.git.origin_web(repo.path)
            except UnavailableError:
                return None
        return self._known[repo.name]


async def _facts(deps: Deps, repo: TrackedRepo, merges: list[MergeFact]) -> dict[str, TicketFlow]:
    """The merged tickets, the tickets that name them as their cause, and those in flight."""
    tickets = deps.ports.tickets
    found = await tickets.flow_facts(repo.name, stages=sorted(IN_FLIGHT_STAGES))
    merged = sorted({m.ticket for m in merges if m.ticket is not None})
    if merged:
        found += await tickets.flow_facts(repo.name, ids=merged)
        found += await tickets.flow_facts(repo.name, causes=merged)
    return {t.id: t for t in found}


async def flow_page(deps: Deps, web: WebAddresses, range_name: str | None) -> FlowPage:
    """The Flow page for the window `range_name` names (any other text reads as seven days)."""
    now = deps.seconds()
    name, length = range_of(range_name or "")
    since = now - length
    repos = await deps.repositories()
    async with deps.uow() as session:
        store = MetricsRepository(session)
        merges = await store.merges_since(since, [r.name for r in repos])
        cuts = {r.name: await store.cuts(r.name) for r in repos}
    tickets: dict[tuple[str, str], TicketFlow] = {}
    in_flight: list[InFlight] = []
    starts: dict[str, dict[str, float]] = {}
    addresses: dict[str, str | None] = {}
    for repo in repos:
        own = [m for m in merges if m.repository == repo.name]
        facts = await _facts(deps, repo, own)
        tickets.update({(repo.name, t.id): t for t in facts.values()})
        in_flight.extend(
            InFlight(repo.name, t, cuts[repo.name].get(t.branch))
            for t in facts.values()
            if t.stage in IN_FLIGHT_STAGES and t.branch and not t.archived
        )
        built = await deps.ports.runs.build_starts(repo.name, instant(since), instant(now))
        starts[repo.name] = {ticket: at.timestamp() for ticket, at in built.items()}
        if own:
            addresses[repo.name] = await web.of(deps, repo)
    runs = await deps.ports.runs.since(instant(since - COST_LOOKBACK_S))
    return assemble_flow(
        range_name=name,
        now=now,
        merges=merges,
        tickets=tickets,
        runs=runs,
        build_starts=starts,
        in_flight=in_flight,
        web=addresses,
    )
