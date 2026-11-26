# Writing an MCP tool

Tools live in a module's `tools.py` (or `tools/` package) and are added by its `register_tools`.

```python
@mcp.tool(annotations=READ_ONLY)
async def list_things(limit: PageLimit = 25, cursor: str | None = None) -> Page[Thing]:
    """List the things of the caller's ticket, newest first. Use when ..."""
```

Rules the surface tests hold (`tests/integration/platform/test_mcp_surface.py`):

- **Name** `verb_noun` in lower case, the verb one of `get list create update post read write submit
  dismiss search propose ask answer start stop run`.
- **Description** says when to use the tool (`Use when`, `Use to`, `Use first`, `Use before`) and
  stays within 600 characters.
- **Annotations** from `platform/mcp/hints.py`: `READ_ONLY`, `APPENDS`, `SETS` or `REPLACES`; a
  tool that reads changes nothing and a tool that writes is not read only.
- **Inputs** refuse extra fields; put every limit in the schema (`PageLimit`, `Field(le=...)`,
  `max_length`) so a call outside it is refused before the tool runs.
- **Output** is a pydantic model (an object); a list tool returns `Page[T]` with `next_cursor`
  (`platform/mcp/results.py`).
- **Errors** are the platform's error classes; their sentence reaches the model as the tool error.

Access: add the tool to `TOOLS` in `platform/mcp/policy.py` with who may call it, and scope its
ticket with `scope.scope_ticket` (which also holds a coordinator to its repository), never
`policy.scope_ticket` directly. `tests/unit/platform/test_mcp_policy.py` holds the access matrix by hand.

The tool lists each caller sees are pinned in `tests/support/golden/mcp/`. After a change, read the failing
diff, then bless it: `CODE_FACTORY_BLESS=1 uv run pytest --no-cov tests/integration/platform/test_mcp_surface.py`.
A build run's list stays under 15,000 bytes of what the model reads.
