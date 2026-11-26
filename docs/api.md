# The HTTP API and how the app is served

One process, one port: `code-factory serve` answers the Vue app, its API under `/api`, Swagger
and the MCP server at `/mcp`. Layers and file roles are in [architecture.md](architecture.md).

## Serving the app

| Path | Answer |
|---|---|
| `/api/...` | the API; an unknown path is a problem+json 404, never the page |
| `/assets/<hashed name>` | the build's file, `Cache-Control: public, max-age=31536000, immutable`; an unknown name is a 404 |
| `/`, `/favicon.svg`, `/manifest.webmanifest`, `/icon-*.png`, `/theme-early.js` and any other path | the build's file when there is one, else `index.html` (the client routes), with `no-cache` and an `ETag` (`304` on `If-None-Match`) |
| `/owner/<value>` | the sign-in link (below) |
| `/mcp/` | MCP, with bearer tokens |

`web/` builds into `src/code_factory/platform/web/dist` (`pnpm --dir web build`): package data under
the module root, ignored by git, so a wheel carries it. The server reads the folder once when it is
built (`platform/web/webapp.py`) and answers from memory; with no build, `/` answers `503` naming the
build command and the API still works. Every answer carries `X-Code-Factory-Build`, the SHA-256 of
the sorted `shasum -a 256` listing of the build; an open tab compares it with the first it saw.

Development: `pnpm --dir web dev` runs Vite on `localhost:5173` and proxies `/api` and `/owner` to
`127.0.0.1:4000` (`web/vite.config.ts`; `CODE_FACTORY_PORT` names another port). The proxy rewrites
`Host` and `Origin` to the server's own, which the host guard and the same-origin rule require. Open
the sign-in link with Vite's address (`http://localhost:5173/owner/<value>`) so the cookie belongs to
the host the page is loaded from.

Every response carries the platform's Content-Security-Policy (`script-src 'self'`, no inline
script; `style-src 'self' 'unsafe-inline'`, since the chart sets its colours as inline styles); the
build satisfies it (`assetsInlineLimit: 0`, `theme-early.js` is a file).

## Sign-in

`code-factory serve` prints `serving on http://127.0.0.1:<port>` and then a link,
`sign in: http://127.0.0.1:<port>/owner/cfn_...`. The link carries a one-time value (60 seconds);
opening it swaps it for a session and answers `303` to `/` (or to `?to=<path of the board>`) with
`code_factory_owner=cfs_...; HttpOnly; SameSite=Strict; Path=/`. On a terminal `serve` also opens that link in the default browser (not with `--no-open` or
`CODE_FACTORY_OPEN=false`); `code-factory open` does the same for a server that already runs, and
`code-factory sign-in` prints a new link. Every link names `127.0.0.1`, and the session cookie belongs to that one host name: a page asked on `localhost` or `[::1]` (a `GET` or `HEAD` outside `/api` and `/mcp`) answers `308` to the same path on `127.0.0.1`, so a sign-in link or a bookmark on another loopback name lands where the session is (`HostGuard`, `platform/web/middleware.py`). The tokens are the auth module's (`auth/service.py`); a session is never accepted as an
MCP bearer, nor an MCP token as the cookie.

Guard (`platform/web/guard.py`, outermost first): every `/api` path except `/api/health`,
`/api/ready` and a pushed reply link (GET and POST of `/api/reply/` and 64 lowercase hex
characters, whose token is its only credential, `push/routes.py`) and an agent's hooks
(`/api/hooks/`, which take a run's or the owner's bearer token, `hooks/routes.py`) needs a live
session, `403` with the sentence naming the link (reads and writes have
their own). A change (any method but GET, HEAD, OPTIONS) from another origin (`Origin` or
`Sec-Fetch-Site`) is `403`, a body that is not JSON is `415`, and changes under
`/api/agent-definitions`, `/api/agent-context` and `/api/connections` also need an `Origin`.
Swagger and the OpenAPI document are behind the guard. `/mcp` is outside it: it takes the auth
module's bearer tokens (an owner's, or a run's bound to its ticket and stage), checked on every
request, with host and origin protection; `tests/auth/test_auth_mcp_http.py` holds both protocol
revisions, 2025-11-25 and 2026-07-28, to it.

MCP tokens are opaque and issued by the board itself, not through the specification's OAuth
flow: the owner creates one with `code-factory token create --label <machine>`, a run gets its own
at start, bound to its ticket and stage and revoked at its end. So `/mcp` serves no protected
resource metadata, and a client is configured with the token rather than discovering an
authorization server. Each token may make 120 tool calls a minute (`platform/mcp/rate.py`).

## Errors

Every error is RFC 9457 `application/problem+json`: `type` (`about:blank`), `title` (the status
phrase), `status` and `detail`, the sentence (`platform/web/errors.py`). A body that does not
validate is a `400` with `errors`, each a JSON pointer (`/body/<field>`) and what is wrong there.
Services raise the platform's error classes and the status follows from the class; routes map
nothing themselves.

## Requests

- Bodies are typed models that refuse unknown fields, so `/api/docs` is the contract.
- A create answers `201` with `Location`, the address that reads the new thing back.
- A DELETE carries no body: what it removes is named in the path.
- The board, the inbox and the served files answer `304` to their own `ETag` in `If-None-Match`.
- A ticket page's `ETag` tags its `ticket` fields; an edit (`PATCH /api/tickets/...`) with that
  tag in `If-Match` applies only while the fields are unchanged, else `412`. The rest of the page
  holds times measured against the clock, so the page itself is not answered `304`.

## Routes

The code is the list: `/api/openapi.json` and `/api/docs` show it. Each module's `routes.py` is
thin: it calls the module's service, with no session in a signature.

The board's reads (`board/routes.py`) are served by `BoardService` (see [Board](board.md)).
The tickets, stages, sessions, talk, releases, repositories and settings services supply the
board. Runs, checks and delivery register the ports that supply run status, check verdicts and
pull request state. Also served: saved views (the
`board_views` table), the inbox count (open questions), findings (list and close), answers,
comments and messages (talk), coordinator undo and `POST /api/undo/{token}` (undo), mock images and
the diff (git; empty for a repository that is not tracked) and the Team page (`team/routes.py`, its
sources are `board/adapters.py` until the owning modules register theirs). The scorers are the
evals module's (`evals/routes.py`).

`POST /api/repositories` (`commands/routes.py`) tracks a repository from the browser, as
`code-factory track` does from a terminal: `path` must be an absolute folder that exists and lies in
a git repository, and the repository's main checkout is tracked, so a worktree's folder tracks its
repository. Each refusal is a 400 sentence naming the path and what to give instead.

Every ticket write goes through the ticket-writes service (`ticket_writes/routes.py`), which holds
the stage rules, undo and refusals. A move to Build needs a branch. The Review column also expects
a pushed branch and a recorded pull request. The ticket's **Review with an agent** action can
run a review of a completed local Build before shipping.

## The contract harness

`tests/contract/contract_catalogue.py` lists every route the web app calls with the module that
answers it and the golden (`tests/golden/formats`) or hand spec its answer is judged against.
`contract_shapes.py` compares shape (keys, their order, types, nullability, optional keys across list
elements), never values. `test_contract_catalogue.py` fails for a call in `web/src` missing from the
catalogue, and for a route served before its module left `PENDING_OWNERS` (or the reverse);
`test_contract_answers.py` holds each served route to its shape.

## Browser tests

`web/e2e` starts `uv run code-factory serve` per test with `CODE_FACTORY_PORT=0` (a free port,
printed) and `CODE_FACTORY_STOP_AT_EOF=1` (the server stops when its stdin closes, so a killed test
worker takes its board with it). Each board has a schema of its own in the test database named by
`CODE_FACTORY_DATABASE_URL` (the role cannot create databases): `code-factory sample-prepare`
creates and migrates the schema named by `CODE_FACTORY_DB_SCHEMA`, `sample-load <name>` fills it
through the services, `sample-drop` removes it. The three refuse a database whose name does not end
in `_test` and the default schema. Every sample holds the owner's fixed session, which
`web/e2e/owner.ts` sends as the cookie.

```sh
export CODE_FACTORY_DATABASE_URL=...   # a database ending in _test
pnpm --dir web build
CODE_FACTORY_E2E_BUILT=1 pnpm --dir web e2e e2e/served_app.spec.ts
```
