# A split run files its child tickets itself

`POST /api/tickets/{repository}/{id}/split` with a brief starts a run of stage `split` that files the
brief's pieces as child tickets with the `create_ticket` MCP tool, at most 50, the parent set for it.

**Why.** No proposal waits for an accept: the owner reviews the children on the board, where they
can be edited or deleted like any ticket, instead of in a second editing surface for tickets that
do not exist yet.

**What follows.** The MCP policy gives a split run its 50-ticket quota and sets the parent
(`platform/mcp/policy.py`, `tickets/tools/tickets.py`); the prompt is `runs/rules/split.py`.
