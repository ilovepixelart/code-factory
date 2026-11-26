# code-factory

Python 3.14, async first: FastAPI (HTTP), FastMCP (MCP), PostgreSQL through SQLAlchemy asyncio and
asyncpg, Alembic migrations, a Vue app in `web/` (pnpm, Node 26). The repository is local: no
remote, no push. Version `0.y.z` until it is used in production.

## Layout

A modular monolith. The rules and their tests are in `docs/architecture.md`; the other `docs/`
pages cover async, the UI, the ticket and memory store and the factory figures.

```
src/code_factory/
  platform/   shared kernel: config, db, web, mcp, process, runtime, text, ...; imports no module
  <module>/   one domain area, one file per layer (a layer it does not need has no file)
  app.py      composition root: MODULES, builds the services, the `code-factory` entry point
alembic/      one migration history for every module
tests/        mirrors the modules; test file names are unique across tests/
web/          the Vue app
```

Layers inside a module, each importing only those below it:

| Layer | Files |
|---|---|
| entry | `module.py` (the `Module` description, the only file `app.py` imports) |
| edges | `routes.py` (FastAPI, thin), `tools.py` (MCP, thin), `cli.py` (subcommands) |
| use cases | `service.py`: the module's public API |
| IO | `adapters.py` (git, gh, processes), `repository.py` (queries), `ports.py` (what it reads from other modules) |
| data | `tables.py` > `rules.py` (pure domain rules) > `models.py` (DTOs and enums) |

Another module is reached only through its `service` and `models`. A file over 400 lines becomes a
package of the same name. The contracts are in `pyproject.toml` (`[tool.importlinter]`), run by
`tests/test_architecture.py`; a violation is fixed, never baselined.

Adding a module: its package with a `module.py`, an entry in `MODULES` in `app.py` (after the
modules it uses), its name in the `module-layers` contract, tables on `platform.db.Base` with an
Alembic revision, tests in `tests/<name>/`. `docs/architecture.md` has the `Module` fields;
`tests/test_architecture.py` fails when the contract or the tables are forgotten.

## Commands

| Command | Does |
|---|---|
| `sh scripts/gate.sh` | the gate, run before every commit: static checks, then pytest and the web checks side by side |
| `uv run pytest --no-cov tests/test_x.py` | a subset (add `-n 4` for workers) |
| `pnpm --dir web test` (or `lint`, `typecheck`, `build`) | one web check; `web/e2e` needs a server and is not in the gate |
| `sh scripts/start.sh` | sync, build the web app, check the database, serve: the board in one command |
| `sh scripts/demo.sh` | the demo board on 4321, data on every page: the way to look at and polish the web app |
| `sh scripts/site.sh` (or `build`) | the landing page in `site/`, served live on 8100 |
| `uv run code-factory serve` (or `mcp`, `db upgrade`, `db check`) | run it |
| `uv add X` / `uv remove X` / `uv version --bump minor` | the only way dependencies and the version change |
| `uv run alembic revision --autogenerate -m "..."` | a draft migration, then edit it by hand |
| `sh scripts/audit.sh` | `uv audit` of the lock file (network; not in the gate) |

A `CODE_FACTORY_DATABASE_URL` that names a user and no password takes it from the keychain item
`code-factory-postgres` (`platform/keychain.py`), so no shell or service file holds it.
The gate and the tests read the database password from the macOS keychain
(`security find-generic-password -a code_factory -s code-factory-postgres -w`) and use
`code_factory_test`, or the database in `CODE_FACTORY_TEST_DATABASE` (it must match
`[a-z0-9_]+_test`) so worktrees do not share one. Worker counts: `CODE_FACTORY_TEST_WORKERS`
(pytest, 3) and `CODE_FACTORY_WEB_TEST_WORKERS` (vitest, 2).

## Rules

- Test first, one behaviour at a time: see the test fail for the right reason, make the smallest
  change, then break the change once and see the test fail. Expected values come from outside the
  code; both sides of every guard; failure paths with their specific error.
- Tests never touch the `code_factory` database and never `create_all` (`tests/database_guard.py`);
  the isolation per test and per xdist worker is explained in `tests/conftest.py`.
- No blocking call in `async def`; background work belongs to the lifespan's task group;
  `CancelledError` is never swallowed (`docs/async.md`, `tests/test_event_loop_blocking.py`).
- Migrations: read and edit every generated file; schema and data in separate revisions; the app
  checks the revision at startup and never migrates (`docs/architecture.md`).
- The web app follows `docs/design.md` and `docs/ui.md`: theme tokens, shared components, no
  inline handlers (the Content-Security-Policy refuses them) and no inline styles of our own (only
  shadcn-vue's chart sets them).
- ruff `select = ["ALL"]` (line length 100, complexity 15) and ty with every rule an error;
  `# ty: ignore[rule]` only with a reason.
- Errors are sentences naming what is wrong and the command that repairs it. The password never
  appears in a log, an error or a `repr` (`SecretStr`).
- No em or en dashes. Comments state constraints the code cannot.
- The previous implementation is not named anywhere; tickets are `CF-<n>`
  (`tests/test_no_old_name.py`).
- Commits: one logical change each, imperative subject under 72 characters, a factual body, no AI
  attribution, never a secret, `.env`, cache or build output.
