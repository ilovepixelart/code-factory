# Errors are problem+json

Every error the API answers is RFC 9457 `application/problem+json`: `type` (`about:blank`),
`title` (the status phrase), `status` and `detail`, one sentence naming what is wrong and what
repairs it. A body that does not validate is a 400 with `errors`, each a JSON pointer
(`/body/<field>`) and what is wrong there.

**Why.** One shape for every failure lets the web app, MCP clients and scripts read errors the same
way, and the sentence is written for the person who caused it.

**What follows.** Services raise the platform's error classes (`platform/errors.py`); the status
follows from the class (`platform/web/errors.py`) and no route maps errors itself. MCP tools give the
same sentence as a tool error (`platform/mcp/errors.py`). `tests/platform/test_api_errors.py` holds
the shape.
