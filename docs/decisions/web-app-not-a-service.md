# The board is a web app, started with serve

code-factory runs as `uv run code-factory serve` while the owner wants it. Nothing is installed into
the operating system: no login item, no launchd agent, no background service.

**Why.** It is a web app. Hooks, MCP, push messages and the follower work while it runs; when it is
stopped they wait, and the owner decides when that is.

**What follows.** There is no zero-downtime handover between board processes and no deploy command;
a newer build is a restart of `serve`.
