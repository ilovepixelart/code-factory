# Permission request

How a run's PermissionRequest hook is settled by the board's policy, a standing rule, the reviewer or the owner, and how the answer gets back to the agent.

Source: `src/code_factory/hooks/adapters/hook.py`, `src/code_factory/platform/web/guard.py`, `src/code_factory/hooks/routes.py`, `src/code_factory/hooks/service/base.py`, `src/code_factory/hooks/service/permission.py`, `src/code_factory/hooks/service/neighbours.py`, `src/code_factory/runs/service/permissions.py`, `src/code_factory/runs/adapters/reviewer.py`, `src/code_factory/runs/rules/hook_output.py`, `src/code_factory/agents/rules/hooks.py`, `src/code_factory/agents/rules/permissions.py`, `src/code_factory/inbox/service/neighbours.py`, `src/code_factory/runs/routes.py`

```mermaid
sequenceDiagram
    autonumber
    participant Claude as claude (run)
    participant Hook as hook.py permission
    participant Route as POST /api/hooks/permission
    participant Hooks as HookService
    participant Perm as PermissionService
    participant Reviewer as reviewer command
    participant DB as permission tables
    participant Inbox as InboxService
    actor Owner

    Claude->>Hook: PermissionRequest payload on stdin (hook timeout 600 s)
    Hook->>Route: POST with Bearer CODE_FACTORY_MCP_TOKEN, sandboxed flag, HTTP read limit 600 s
    Route->>Route: AuthService.verify_token, else 401
    Route->>Hooks: permission(actor, payload, sandboxed, alive)
    alt actor has no ticket or no run
        Hooks-->>Route: None
    else
        Hooks->>Perm: request(run, payload, wait 540 s) in a task
        Perm->>Perm: policy (kit.routine): words outside the tree deny, a listed board read allows
        alt policy decided
            Perm->>DB: decision by policy
            Perm-->>Hooks: allow, or deny with the policy's words
        else policy refused 3 in a row
            Perm->>Perm: escalate to the owner with a note
        else no policy answer
            Perm->>DB: standing rules
            alt the request's kind is a rule
                Perm->>DB: decision by owner, a standing rule of the owner
                Perm-->>Hooks: allow
            else a reviewer is configured, input under 64 KiB, reviewer still open
                Perm->>Reviewer: sh -c command, request on stdin, 60 s
                Reviewer-->>Perm: exit 0 or not, first 4 KiB
                Perm->>DB: review, and a decision by reviewer unless the verdict is owner
                Perm-->>Hooks: allow, or deny with the reviewer's reason
            end
        end
        opt still unsettled: the owner
            Perm->>DB: add pending request (id, tool, summary, kind, note)
            Inbox->>Perm: pending(now) for GET /api/inbox
            Owner->>Inbox: reads the permissions section
            loop until answered, withdrawn or 540 s
                Perm->>DB: re-read the request every 2 s or on the in-process event
                Hooks->>Route: is the client still connected, every 0.25 s
            end
            alt owner answers
                Owner->>Perm: POST /api/permissions/{request_id}/{allow or deny}
                Perm->>DB: answer, decision by owner
                Perm->>Perm: set the waiter's event
                Perm-->>Hooks: allow, or deny with interrupt (The owner denied this request.)
            else the hook closed
                Hooks->>Perm: cancel the task, it withdraws the request (5 s cleanup)
                Hooks-->>Route: None
            else 540 s passed
                Perm->>DB: withdraw the request
                Hooks-->>Route: deny, Nobody answered this permission request from the board in time
            end
        end
        Hooks->>Hooks: record a permission event on the ticket (tool, decision, waited)
    end
    Route-->>Hook: 200 {"output": hook JSON or null}
    Hook-->>Claude: prints hookSpecificOutput.decision, or nothing
```

## Notes

- The waits line up: the runtime kills the hook at 600 s (`PERMISSION_TIMEOUT_S`), the hook's socket gives up at 600 s, the board answers by 540 s (`WAIT_S` in both `hooks/service/base.py` and `runs/service/permissions.py`).
- An owner's answer to a request older than 540 s is refused with 409 (`this request waited longer than 9 minutes, ...`), one already answered with 409, one whose hook closed with 404 (`the agent stopped waiting for this answer`).
- Only the owner's deny interrupts the run; a deny by the policy, the reviewer or the timeout carries words so the run tries another way.
- `/api/hooks/` routes pass the owner's cookie guard and check the bearer token themselves.
- The hook prints nothing and exits 0 on any failure: no token, a non-loopback `CODE_FACTORY_URL`, a refused connection, a non-200 answer or a body over 1 MiB.
- The sandbox allowance (a Bash call of a sandboxed run is allowed when no reviewer is configured) is not reachable from the hook: `PermissionsAdapter.request` drops the `sandboxed` flag, and `RunLauncher` removes every `CODE_FACTORY_` variable, so `CODE_FACTORY_SANDBOXED` is never set for a run.
- On start the run keeper withdraws pending requests made before it started (their waiters died with the previous process); every 30 s it expires requests older than 540 s and prunes decisions older than 90 days.
- A pushed reply link can answer the same request (see `push-and-reply.md`).
