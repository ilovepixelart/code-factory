# The team

`src/code_factory/team` decides which defined agent takes a ticket and why a ticket waits, keeps
each ticket's claim, says what each agent does, and assembles the Team page. The rules are pure
(`team/rules/`, one file per concern, tests in `tests/team/`); the service is `team/service/`.

## Ports, not imports

The team imports no domain module. The modules it reads from (agents, runs, tickets, checks,
inbox, sessions, and whichever runs land jobs) register an adapter in their own `provide`:
`services.add(AgentSource, adapter)`, with the Protocols in `team/service/ports.py` and the shapes
in `team/models/sources.py`. Each port is looked up when a call uses it (`module.py`), so a module that
registers late, or not yet, only fails a call that needs it: `UnavailableError`, naming what is
missing. `claim`, `beat` and `release` need no port at all. A provider imports `team.service` and `team.models`, never the reverse.

## Claims

A ticket's claim is a row (`team_leases`, one per ticket by a unique constraint, plus the run ids
under it in `team_lease_runs`). Whether it holds is never stored: `rules.holds` reads the run
source, so a run ended in the runs table cannot leave a claim looking active. A claim holds while a
run under it is active; with none recorded, for 60 s after its last beat. The runs a decision reads
come from several port calls; for a run listed by more than one, `runs_on_ticket` wins, since it
alone reports live tokens.

- Every write to claims runs under two locks, taken in this order: an `asyncio.Lock` of the
  process, then a Postgres advisory lock (`repository.LOCK_KEY`). Without the advisory lock two
  tickets read the same free agent (`tests/integration/team/test_team_concurrency.py` shows it with two services over committed
  sessions, which the savepoint fixture cannot). Without the process lock, claims waiting for the
  advisory lock each hold a pooled connection that the lock holder's own port reads need
  (`tests/integration/team/test_team_claims_pool.py`, a pool of two).
- `claim_for_run` reads agents and runs, claims and picks in that one transaction. A run that ends
  after its claim was taken again calls `end_claim(ticket, run_id=...)`, which refuses to delete a
  claim the run is not recorded under.
- A ticket id is written `CF-<n>` without leading zeros: claims are keyed by the written id.
- The table names the ticket by number (`ticket_number`, as the other modules do); the service and
  the rules use the id `CF-<n>`.
- The module's `background` hook starts `TeamService.run_keeper` as the `team-keeper` background
  task (a pass every 5 s, the first one interval in; a failed pass is logged and the loop goes on); a 60 s claim and a 5 s
  beat tolerate 11 missed beats.

## The Team page

`TeamService.now()` reads every port together, each under a 10 s timeout, in two phases (tags
decide the cycle, the cycle decides how far back tickets and first commits reach). One failed port
fails the page with `the team page could not read <port>`; there is no partial page. Git (tags and
first commits) is the only thing the module reads itself, through `adapters.GitFacts`: a 15 s cache
per repository with one git at a time per repository, at most four across repositories, and an
empty answer plus a warning when git fails, is slow or prints more than 4 MiB (a cut log would
drop the oldest commits, which are the ones first commits need).

## Answers

Models serialise as the web app reads them with `model_dump(by_alias=True)`: `Cycle.from_` is
`from` and `Peek.kind` is `type`. `Doing` and `Last` leave out their unset keys. The shape of the
page is pinned by `tests/support/golden/team/now.json` and checked against `web/src/lib/teamNow.ts`
(`tests/unit/team/test_team_page_wire.py`); regenerate the golden with `CODE_FACTORY_BLESS=1` and read
the diff.
