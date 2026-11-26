# MCP request

How one MCP tool call over HTTP at `/mcp` with a bearer token is verified, guarded, run and answered.

Source: `src/code_factory/app.py`, `src/code_factory/platform/web/app.py`, `src/code_factory/platform/mcp/http.py`, `src/code_factory/platform/mcp/server.py`, `src/code_factory/platform/mcp/verifier.py`, `src/code_factory/platform/mcp/access.py`, `src/code_factory/platform/mcp/rate.py`, `src/code_factory/platform/mcp/errors.py`, `src/code_factory/platform/mcp/policy.py`, `src/code_factory/auth/service.py`

```mermaid
sequenceDiagram
    autonumber
    participant Client as MCP client (a run's claude, or the owner)
    participant Web as web layers (RequestId, SecurityHeaders, HostGuard, ErrorBoundary)
    participant HTTP as FastMCP streamable HTTP app at /mcp
    participant Verifier as ActorTokenVerifier
    participant Auth as AuthService
    participant Errors as DomainErrors
    participant Guard as Guard
    participant Rate as CallRate
    participant Tool as the module's tool (tools.py)
    participant Service as the module's service

    Client->>Web: POST /mcp/ tools/call, Authorization Bearer token
    Web->>Web: Host must be localhost, 127.0.0.1 or [::1] on the port, else 400
    Web->>HTTP: forward
    HTTP->>HTTP: Host and Origin validation (host_origin_protection)
    HTTP->>Verifier: verify_token(token)
    Verifier->>Auth: verify_token(token), a live token's digest, touch last use
    alt unknown, ended, or a role the listener does not take
        Verifier-->>HTTP: None
        HTTP-->>Client: 401
    else
        Verifier-->>HTTP: AccessToken with the Actor in its claims
        HTTP->>Errors: on_call_tool
        Errors->>Guard: on_call_tool
        Guard->>Guard: resolve(): the Actor from the access token claims
        alt policy.may_call(actor, tool) is false
            Guard-->>Errors: ToolError forbidden: tool is not available to a build run. whoami says what is.
        else
            Guard->>Rate: wait(token id)
            alt 120 calls in the last 60 s
                Rate-->>Guard: seconds to wait
                Guard-->>Errors: ToolError rate limited: 120 tool calls in the last minute. Wait n s, then call again.
            else
                Guard->>Guard: set current_actor
                Guard->>Tool: call_next: FastMCP validates the arguments, then runs the tool
                alt arguments outside the input schema
                    Tool-->>Errors: ValidationError
                    Errors->>Errors: bad arguments: each argument and why. Call again within the tool's input schema.
                else
                    Tool->>Tool: current_actor(), policy.scope_ticket and quotas
                    Tool->>Service: the use case
                    alt CodeFactoryError
                        Service-->>Tool: raises
                        Tool-->>Errors: ToolError masked by FastMCP, cause CodeFactoryError
                        Errors->>Errors: ToolError with the error's own sentence
                    else any other exception
                        Tool-->>Errors: ToolError Error calling tool name (logged with traceback)
                    else
                        Service-->>Tool: result
                        Tool-->>Errors: ToolResult
                    end
                end
            end
        end
        Errors-->>HTTP: ToolResult, or ToolError
        HTTP-->>Client: result, or an error result carrying the sentence
    end
```

## Notes

- `tools/list` passes the same Guard: it answers only the tools the actor's role and stage may call, in the order of `policy.TOOLS`. A run whose stage is not spec, build, review or split sees only `whoami`.
- The rate limit is a sliding window per token, in memory, per listener process.
- Scope refusals come from the tool: a run is scoped to its own ticket (`out_of_scope: this run is scoped to <id>; ...`), and the scope check runs before any lookup, so an existing and a missing ticket are refused alike.
- The mounted server has no lifespan of its own; the HTTP app's lifespan starts the shared runtime.
- Over stdio (`code-factory mcp`) there is no bearer: the process's `CODE_FACTORY_MCP_TOKEN` is verified again on every call, and an ended token answers `forbidden: this token has ended. ...`.
- `Access.roles` (a listener that takes only some roles) exists, but both places that build an `Access` (`app.py`) leave it unset, so the HTTP listener at `/mcp` accepts every role.
- `/mcp` is outside the owner's cookie guard; the bearer token is its only credential.
