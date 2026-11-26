# Running code-factory

Choose [Local mode](#local-mode) to use Claude Code or Codex installed on your machine.
Choose [Server mode](#server-mode) to run the board and database in Docker.

## Server mode

With the Docker Compose plugin available and the source checked out, run:

```sh
sh scripts/compose.sh
```

Open the printed one-time sign-in link in your browser. The script creates a database password,
starts PostgreSQL, applies migrations, and waits for the board. Docker builds the image on the
first run. If you have a prebuilt compatible image, set `CODE_FACTORY_IMAGE` to its name before
launching. Use `CODE_FACTORY_COMPOSE_PORT=4010` if port 4000 is in use. PostgreSQL and the board
state are stored in named volumes. `docker compose stop` stops the stack and retains the data.
Run the script again for a fresh sign-in link. After updating the source, use `docker compose build factory`
to rebuild the app image.

Clone a Git repository into the stack's repository volume, then track it:

```sh
docker compose exec factory git clone <repository-url> /repositories/my-repo
docker compose exec factory code-factory-container track /repositories/my-repo
```

Server mode binds the board to loopback and keeps its own repository volume. Use
[Local mode](#local-mode) for live runs with the coding tools installed on your machine.

## Local mode

Install and start Docker with Compose. Install [uv](https://docs.astral.sh/uv/) 0.13.9 or newer,
Node 26 or newer, and pnpm 12.14. Install and sign in to Claude Code or Codex. Codex also needs the
`srt` sandbox executable on your PATH. See [Agents](agents.md#using-an-installed-coding-cli).

From the source checkout, run:

```sh
sh scripts/start.sh --local
```

This installs the locked dependencies, builds the web app, and starts a dedicated PostgreSQL
container bound to a free loopback port. It generates the database password, applies migrations,
and opens the board signed in. The first run downloads dependencies and may pull PostgreSQL.
The database keeps its data in a Docker volume between launches. In Docker Desktop, the
`code-factory` project contains `postgres` and its one-time `postgres-init` container.
Server mode uses the separate `code-factory-docker` project. The default board port is 4000.
If another app needs that port, run `CODE_FACTORY_PORT=0 sh scripts/start.sh --local` to choose
a free port and print its sign-in link.

Use **Track repository** on the board and give it the absolute path of a local Git checkout.
Then open **Agents → Local harnesses** to set up a coding agent.

Ctrl+C stops the board. To stop its database and keep the data, run:

```sh
docker compose -f compose.yaml -f compose.native.yaml stop db
```

## Bring your own database

Use a source checkout on macOS, [uv](https://docs.astral.sh/uv/) 0.13.9 or newer (it installs
Python 3.14), Docker for PostgreSQL, and Node 26 or newer with pnpm 12.14 to build the web app.
The documented setup uses the macOS keychain for database credentials. The board serves one
owner on the local machine.

### Set up once

1. Store a generated password for the database role in the keychain, then start PostgreSQL 18 with a
   `code_factory` role and database, and a database for the tests:

   ```sh
   security add-generic-password -a code_factory -s code-factory-postgres -w "$(openssl rand -hex 24)"
   docker run -d --name code-factory-dev-postgres -p 127.0.0.1:5432:5432 \
     -v code-factory-dev-pg18:/var/lib/postgresql \
     -e POSTGRES_USER=code_factory -e POSTGRES_DB=code_factory \
     -e POSTGRES_PASSWORD="$(security find-generic-password -a code_factory -s code-factory-postgres -w)" \
     postgres:18-bookworm
   for _ in $(seq 30); do docker exec code-factory-dev-postgres pg_isready -q -h 127.0.0.1 -U code_factory && break; sleep 1; done
   docker exec code-factory-dev-postgres createdb -U code_factory code_factory_test
   ```

2. Put the settings in `.env.local`, which git ignores and only you may read:

   ```sh
   install -m 600 /dev/null .env.local
   cat > .env.local <<EOF
   CODE_FACTORY_DATABASE_URL=postgresql+asyncpg://code_factory:$(security find-generic-password -a code_factory -s code-factory-postgres -w)@127.0.0.1:5432/code_factory
   CODE_FACTORY_PORT=4000
   EOF
   ```

   A URL without the password (`postgresql+asyncpg://code_factory@127.0.0.1:5432/code_factory`)
   works too: the password is then read from the keychain item `code-factory-postgres`.

3. Install, migrate and build the web app:

   ```sh
   uv sync --locked
   uv run code-factory db upgrade
   pnpm --dir web install --frozen-lockfile && pnpm --dir web build
   ```

### Run

```sh
sh scripts/start.sh
```

The script syncs the dependencies, installs and builds the web app, runs `code-factory db check`
(it never migrates; see [Upgrade](#upgrade)), then `code-factory serve` with the script's
arguments. Once built, `uv run code-factory serve` alone starts the same board.

It serves on `CODE_FACTORY_PORT` (4000) and opens the default browser signed in; it opens nothing
when stdout is not a terminal, with `--no-open` or with `CODE_FACTORY_OPEN=false`. Against a running
board, `uv run code-factory open` signs the browser in again and `uv run code-factory sign-in`
prints a one-time link (valid for 60 seconds). `curl http://127.0.0.1:4000/api/ready` checks it.

The web app on its own, with hot reload:

```sh
pnpm --dir web dev      # Vite on http://localhost:5173, /api proxied to 127.0.0.1:4000
```

## MCP clients

An HTTP client connects to `http://127.0.0.1:4000/mcp/` with `Authorization: Bearer <token>`; make
the token with `uv run code-factory token create --label <machine>` in a shell configured for the
board's database. In Server mode, use
`docker compose exec factory code-factory-container token create --label <machine>`.
A stdio client runs
`uv run code-factory mcp` with `CODE_FACTORY_DATABASE_URL` and `CODE_FACTORY_MCP_TOKEN` set. Runs
get tokens of their own; see [api.md](api.md).

## Track a repository

In Local mode, use **Track repository** on the board. For Server mode, see the
[container checkout steps](#server-mode). From a shell configured for the board's database:

```sh
uv run code-factory track ~/code/my-repo
```

The board files tickets in the tracked repositories. A repository's own settings (checks command,
agents, preview) live in its `.code-factory/config.toml`: [reference/config.md](reference/config.md).
On a repository with a GitHub remote, Factory can push finished branches and open pull requests
automatically. Set `[agents] ship = false` to disable automatic shipping while trying Factory on a
repository. Merging waits for owner approval by default.

## Run the first agent

Use the [Agents setup](agents.md#using-an-installed-coding-cli) to connect a signed-in Claude Code
or Codex CLI. Assign an agent to Spec and Build, and a different agent to Review. In a repository
you want to try, commit a `.code-factory/config.toml` on the default branch. For example, for a
Python project that can run pytest on the host:

```toml
[agents]
review = true
ship = false

[checks]
command = "python3 -m pytest -q"
```

File a small ticket. Set its test pattern before starting Spec if the repository puts tests
outside `tests/`. Read the requirements and spec, and answer any questions in Inbox. When the
ticket reaches Build and the Spec agent has finished, start the Build agent. Once checks pass, use
**Review with an agent** in the ticket's Agent section. With shipping disabled, merge the branch
yourself after reviewing the result. For Factory's pull request and merge actions, use a GitHub
remote, sign in with `gh`, and enable `ship` on that repository. The board waits for owner merge
approval by default.

See the
[host checks example](../.code-factory/config.example.toml) for the fast and full commands used by
this project. To explore the UI without using model quota, use the [sample board](#sample-boards).

## Upgrade

The Local and Server mode launchers migrate their managed databases. With your own database,
`code-factory serve` refuses to start when the schema is behind. Back it up before running the
upgrade (`pg_dump` comes with `brew install libpq` on macOS):

```sh
mkdir -p ~/.local/state/code-factory/backups
PGPASSWORD="$(security find-generic-password -a code_factory -s code-factory-postgres -w)" \
  pg_dump -h 127.0.0.1 -U code_factory -d code_factory -Fc \
  -f ~/.local/state/code-factory/backups/code_factory-$(date +%F).dump
uv run code-factory db upgrade
uv run code-factory db check      # "database is at head"
```

`pg_restore -h 127.0.0.1 -U code_factory -d code_factory --clean <file>` puts a backup back.

## Sample boards

To look at the web app and polish a page, use the demo board: a board in use, with data on every
page, served on its own port.

```sh
sh scripts/demo.sh                    # http://127.0.0.1:4321, opens the browser signed in
```

It rebuilds the schema `demo` of `code_factory_test` on every start and loads the `demo` sample
into it through each module's own service: three git repositories with a dated history under
`~/.local/state/code-factory-demo` (`CODE_FACTORY_DEMO_STATE`), 25 tickets across the columns,
documents, questions, a memory proposal, agents, claims, reviews, check runs, sessions recorded
by the capture hook, releases and a capture. The board includes saved views and a Build limit.
Inbox shows ready, failing and idle pull requests. Factory uses recorded run costs, pull request
outcomes and review-role notes. Flow includes question waits and gate timing budgets. Agents are held,
so the demo never starts a run. It never touches the `code_factory` database or a board on another
port. Benchmarks and Self-improvement stay hidden until their data sources are available.
`web/e2e/demo_pages.spec.ts` visits each visible page over the sample.

The browser tests load the smaller `board` sample (`sample-load board`) into a schema of their
own; the same commands load either by hand:

```sh
export CODE_FACTORY_DATABASE_URL=postgresql+asyncpg://code_factory@127.0.0.1:5432/code_factory_test
export CODE_FACTORY_DB_SCHEMA=demo
uv run code-factory sample-prepare
uv run code-factory sample-load board
CODE_FACTORY_PORT=4321 uv run code-factory serve
uv run code-factory sample-drop       # when done
```
