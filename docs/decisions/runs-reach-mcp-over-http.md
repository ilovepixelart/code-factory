# A run reaches the board over loopback HTTP

A run's MCP server entry is the board's `/mcp/` over HTTP, and its hooks post to `/api/hooks/*`,
both with a token bound to the run, its ticket and its stage, revoked when the run ends.

**Why.** A stdio MCP server started by the run would need the database credentials in the run's
environment. Over HTTP the run holds only its own token, named in its settings as
`${CODE_FACTORY_MCP_TOKEN}` and never written into its command line.

**What follows.** Runs start only on a served board. The run's environment drops every inherited
`CODE_FACTORY_*` variable, so the board's database address and password never reach it
(`runs/service/launching.py`, tested in `tests/integration/runs/test_run_launching.py`). The hook routes pass the
owner's cookie guard and check the bearer token themselves (`hooks/routes.py`).
