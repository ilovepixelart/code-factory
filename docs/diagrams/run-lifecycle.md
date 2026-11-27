# Run lifecycle

How an agent run of a ticket starts, runs inside its wrapper, ends and is recorded.

Source: `src/code_factory/runs/routes.py`, `src/code_factory/follower/service/__init__.py`, `src/code_factory/follower/service/neighbours.py`, `src/code_factory/runs/service/starting.py`, `src/code_factory/runs/service/neighbours.py`, `src/code_factory/runs/service/launching.py`, `src/code_factory/runs/adapters/processes.py`, `src/code_factory/runs/adapters/runner/wrapper.py`, `src/code_factory/runs/service/keeper.py`, `src/code_factory/runs/service/ending.py`, `src/code_factory/team/service/claims.py`

```mermaid
sequenceDiagram
    autonumber
    participant Caller as Owner (POST /api/tickets/{repository}/{id}/runs) or FollowerService
    participant Runs as RunService
    participant Team as TeamService
    participant Agents as AgentService
    participant Git as GitService
    participant DB as runs table
    participant Auth as AuthService
    participant Launcher as RunLauncher
    participant Registry as ProcessRegistry
    participant Wrapper as runner wrapper
    participant Claude as claude
    participant Keeper as run keeper
    participant Checks as CheckService
    participant Stages as StageService

    Caller->>Runs: start(ticket, stage, options, by)
    Runs->>DB: halted? (HaltRepository)
    Runs->>Runs: check the ask: permission mode, split prompt, stage merged, open blockers
    Runs->>Team: claim_for_run(ticket, stage) under the module's advisory lock
    Team-->>Runs: Claim(agent) or ConflictError (claim held, no agent)
    loop each attempt (several only for build with parallel above 1)
        Runs->>Agents: given(agent), probe(given), given(agent) again
        Note over Runs,Agents: a changed fingerprint is a ConflictError, settings changed
        Runs->>Runs: remaining budget, a Spent budget is a ConflictError
        Runs->>Launcher: launch_refusal(given): not claude, or the board not served, is an UnavailableError
        Runs->>Git: start_worktree(repository, ticket, attempt), head_of(tree)
        Runs->>DB: insert Run (id, branch, worktree, log, stage, agent, model, head)
        Runs->>Runs: MemoryExtrasService.deliver(run, ticket, stage)
        Runs->>Auth: issue_run_token(run, ticket, stage, lifetime = limit + 300 s)
        Runs->>Launcher: launch(LaunchPlan)
        Launcher-->>Runs: Launch(argv = python -m code_factory.runs.adapters.runner exit file -- claude command, env, digest)
        Runs->>Registry: spawn(argv, env, cwd = tree, log) in a new session, under 4 start slots
        Registry->>Wrapper: start (stdout and stderr to the run log)
        Wrapper->>Claude: exec, stdin closed, output piped
        Runs->>DB: set_pid (false: a halt ended the row, ConflictError), instructions, memory digest
        Runs->>Team: attach_run(ticket, run)
        Runs->>Runs: record event run.started
    end
    Runs-->>Caller: Started(runs) (HTTP 201)
    Claude-->>Wrapper: output, then exit code
    Wrapper->>Wrapper: copy output to the log, write exit code to runs/{id}.exit by atomic rename
    loop every 2 s
        Keeper->>Runs: collect()
        Runs->>DB: active runs
        Runs->>Runs: exit file, else is the process alive, else UNKNOWN_CODE -1
        Runs->>DB: end(run, RunEnd: exit code, cost, tokens, commits, uncommitted, halted, limited_until)
        Runs->>Registry: end_leftovers (SIGKILL what remains of the group)
        Runs->>Auth: revoke_run(run)
        Runs->>Runs: record event run.ended
        Runs->>Git: fetch_back(repository, tree, branch) before the commits are read; refusal recorded as branch_refused
        opt run stopped (exit -15)
            Runs->>Git: save_work (keep the tree's unfinished work in a ref)
        end
        opt a build run's commits were fetched back
            Runs->>Checks: queue_head(ticket, newest commit)
            Runs->>Stages: fix_committed(ticket): a ticket a review returned follows its evidence again
        end
        opt a review run that was not stopped
            Runs->>Stages: apply_review(ticket, run, head): a pass is recorded, changes return the ticket to Build
        end
        Runs->>Team: end_claim(ticket, run)
        Runs->>DB: settle(run)
    end
```

## Notes

- Claude Code and Codex launch on a served board. Codex requires an agent connection. The launcher checks these requirements before creating a tree or a run row.
- Any failure after the claim undoes what the start made (`_abandon`): the process is stopped, the row ended with exit -1 and the reason, the token revoked, a tree this start made removed with the branch it gave the ticket (a tree it found, and a branch the ticket had, stay), and the claim released when no earlier attempt holds it.
- The follower starts queued tickets every `CODE_FACTORY_FOLLOWER_SECONDS` (default 5) with `by="board"` and `looping` true except for review; a refusal becomes the queue note `not started: <sentence>`, which the Inbox's stopped section shows. A ticket whose newest runs failed in a row waits `retry_wait` (10 s doubling, at most 300 s) after the last one ended, and after `FAILURES_CAP` (5) failures in a row waits for the owner with a `not started:` note; one whose last run ended on a usage limit waits until it lifts (`follower/rules/queue.py`). With `[agents] review` on, a ticket in Review is due a review run when no review run ended since its last build run, and a ticket a review returned to Build is due a fix run until a build run started after the return commits. Each follower step is bounded by 120 s.
- The process wrapper enforces `max_seconds` or the repository's `run_timeout` (3600 seconds by default). It records the timeout and ends the process group even if the board is offline. The run token gets 300 seconds of grace.
- `looping` is recorded on the run row; nothing restarts a run because of it.
- The wrapper reads an output redaction file named by `CODE_FACTORY_OWNER_CONTEXT`, but `RunLauncher` strips every `CODE_FACTORY_` variable from the run's environment and nothing writes the patterns file, so the output is copied unredacted.
- Both launchers then set `CODE_FACTORY_RUNS_DIR` to the exit file's folder. The wrapper writes the exit file only when its resolved path is a `<run id>.exit` directly in that folder, and removes the variable before the agent starts.
- A stop (`POST /api/runs/{run_id}/stop`) sends SIGTERM to the group and SIGKILL after 3 s; `POST /api/agents/stop` holds every start and stops every active run. A spawn that does not start in 10 s is an `UnavailableError`.
- A row with no pid after 60 s is ended with `the run never recorded a process, so the board ended it`. The keeper never signals a run on its own: runs outlive the board, and the first pass after a restart collects what ended meanwhile.
- Each settle step is safe to repeat; a settle that fails is retried on the next pass (`unsettled`).
