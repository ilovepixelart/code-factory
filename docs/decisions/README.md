# Decisions

One page per decision that shaped the design: what was decided, why, and what follows from it.

| Decision | In short |
|---|---|
| [problem-json-errors.md](problem-json-errors.md) | Every error is RFC 9457 problem+json with one sentence |
| [typed-request-bodies.md](typed-request-bodies.md) | Every request body names its fields and refuses others |
| [rest-conventions.md](rest-conventions.md) | 201 with Location, DELETE without a body, offset paging kept |
| [ticket-etag.md](ticket-etag.md) | A ticket's ETag tags its fields, not its page |
| [schema-keyed-locks.md](schema-keyed-locks.md) | Advisory locks are keyed by schema |
| [runs-reach-mcp-over-http.md](runs-reach-mcp-over-http.md) | A run reaches the board's MCP and hooks over loopback HTTP |
| [split-files-directly.md](split-files-directly.md) | A split run files child tickets itself |
| [keychain-password.md](keychain-password.md) | A URL without a password takes it from the keychain |
| [web-app-not-a-service.md](web-app-not-a-service.md) | The board is a web app started with `serve`, nothing installed into the OS |
| [growth-not-budgets.md](growth-not-budgets.md) | Speed tests assert growth, not a time budget |
