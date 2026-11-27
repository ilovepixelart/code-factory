# Agents

The `agents` module keeps the agents and model connections of this machine, holds provider keys
in the operating system's credential store, and supplies the pure parts of starting an agent.
Runtimes are `claude` and `codex`.

## Using an installed coding CLI

Start [Local mode](quickstart.md#local-mode), then open **Agents → Local harnesses** to see which
coding executables Factory can find on your machine.
Use a harness's setup button to open an agent form with that harness selected. Availability
checks the executable on the server's trusted PATH. Account sign-in and model setup are separate.

In Agents, choose Claude Code and leave the connection unset to use the machine's Claude Code
login. To use Codex with ChatGPT, sign in with `codex login`, create a `codex-login` connection in
Factory, and choose a model from the connection's account catalog. Factory checks availability
before it creates the run's checkout. Codex runs also require
`srt` on the Factory host. Assign the agent to Build and start a Build run on a ticket. Factory
creates an isolated checkout and records the run's output and reported token usage.

A Build must leave clean, fetched commits whose Git tree differs from the starting tree.
Factory queues the repository's configured checks against the fetched result.

## Runtime verification

Run `uv run --no-sync python scripts/replay_runs.py` during a fix round. Add `--base REF` to
replay the same four acceptance cases on a trusted Git revision and the working tree. Each
revision gets a separate PostgreSQL test schema. The cases use synthetic CLI events and report
the first mismatching checkpoint. A setup error or skipped case invalidates the comparison.

Add `--live` before merging a runtime change to run a real Build with each signed-in CLI on a
temporary Factory board. Each Build must make one commit and pass the fixture repository's
configured check. The live trial uses model quota. It runs only when selected explicitly.

When a review uncovers a recurring runtime failure, propose a memory entry for the reason behind
the correction and add a fixture that exercises the behavior. Use the scenario and checkpoint
to group repeat failures. Have QA review changes to acceptance expectations. Ticket-specific
held-back cases can use the existing private QA files.

## Fix-round cap trial

Use the pipeline evaluation runner to compare two and three CI or conflict repair rounds on the
same cases. The runner checks out the same commit twice, disables shipping, and sets each arm's
repository `[agents] fix_rounds`. The review round cap and all selected pipeline steps stay the same.
Exercise both caps through the follower in the isolated driver.
Save the following as a TOML manifest:

```toml
[fix_round_trial]
cases = ["intermittent-ci", "merge-conflict"]

[[setup]]
name = "cap-two"
fix_rounds = 2

[[setup]]
name = "cap-three"
fix_rounds = 3
```

Run the manifest from the project checkout. The driver path is absolute because the runner starts
it from the temporary checkout:

```sh
uv run --no-sync python scripts/eval_pipeline.py \
  /owner/fix-round-trial.toml /owner/fix-round-results.json \
  /owner/run-isolated-factory-cases
```

The driver uses `CODE_FACTORY_EVAL_CASES`, a JSON array of case IDs. Give each arm a fresh board
state and disposable database, replay the same initial history and inputs, and stop each case at
the same observation deadline. Use local or simulated delivery so the trial cannot ship live
changes. The driver writes one outcome per case to the path in `CODE_FACTORY_EVAL_OUTCOMES`.
For example, one row in the JSON array can be:

```json
{
  "case_id": "intermittent-ci",
  "state": "merged",
  "fix_rounds": 2,
  "agent_cost_cents": 120,
  "owner_cost_cents": 2500
}
```

The state is `merged`, `closed` (closed unmerged) or `open` at the deadline. Count the recorded
CI or conflict rounds, which use `fix_rounds`. Record actual run costs and price measured active
owner time at the same USD hourly rate in both arms. Use `null` for a missing cost and `0` for a
known zero. An unsuccessful driver or an incomplete or invalid report leaves the comparison
empty and makes the runner exit nonzero.

Use the same denominator of all cases in each arm. Check which cases merged under only one cap and
how many stayed open, then compare the total cost difference for cases with complete costs in
both arms. A positive `three_minus_two_cents` means three rounds cost more on those pairs.
Repeat with representative CI and conflict cases, consistent models and acceptance criteria,
and reversed arm order where provider timing may matter. Synthetic cases verify the reporting
and isolation only. Changing the default needs real runs with measurable outcomes and costs
under both caps. The current default is three.

## Recording a completed evaluation

After the runner completes a suite, save its actual result as a JSON receipt. Use a stable
identifier from the runner, such as its CI run and job ID, and the actual completion time with
a timezone. Import it on the machine that hosts the board:

```sh
code-factory eval record smoke --repository my-project --input completed.json
code-factory eval report smoke --repository my-project
```

Use the tracked repository name and the suite name on the command line. A build receipt has
these fields:

```json
{
  "receipt": "ci/8214/build",
  "recorded_at": "2026-11-20T12:00:00Z",
  "kind": "build",
  "setup": {"stage": "build", "runtime": "codex", "model": "measured-model"},
  "runs": 1,
  "pass_at_1": 1.0,
  "pass_k": 1.0,
  "pass_at_k": 1.0,
  "cost": 2.5
}
```

Replace the sample values with the runner's results. Rates are fractions from 0 to 1.
A review receipt uses `kind: "review"` and `caught`, `false_findings` and `failed` for
its rate, mean and failure count. You can include `tokens` and `task_runs` when you have
them. Report cost in USD from measured execution. Omit it or send `null` when unavailable.
Supply `0` only for a measured zero. Reimporting the same result gives the same stored ID.
The same receipt ID with different data is refused within a repository.

The dashboard totals recorded eval suite and judge costs inside the selected UTC window. The
receipt covers the suite's execution, and separately recorded judges contribute their own costs.
The import reads completed results; it does not start an evaluation or run a judge.

## State

| Table | Holds |
|---|---|
| `agents`, `agent_context_versions` | the roster in `position` order, each agent's owner context and up to 20 replaced versions |
| `connections` | name, kind, address and the name of the key (never the key) |
| `agent_model_checks` | one current result per agent, valid while its runtime, connection and model are unchanged |

Columns and constraints: `src/code_factory/agents/tables.py`. Every roster write runs in one
transaction under one advisory lock; probes and model checks run outside any transaction. A rename first enters each rename guard's `frozen(name)` (the lock its own writers take, so a claim that read the roster finishes its lease first), then asks `holds(name)` inside the roster lock, and leaves `frozen` after the commit; each step runs under a 10 s timeout. The claims module must take that same lock around its read of the roster and its lease, and register a guard whose `frozen` takes it.

## Keys

`CredentialStore` reads a key from `security` (macOS) or `secret-tool` (Linux) under the service
`code-factory`, then from the process environment. A value is never cached, logged, put on a
command line or in an error. `code-factory secret set NAME` stores it (the program prompts on the
terminal).

## Undo

A write returns an `UndoStep` holding the target before and after. `AgentService.undo` applies
the inverse only while the target is as it was left, else it refuses with a conflict.

## Starting an agent

`AgentService.kit` (`StartKit`) passes through every public rule the runs module needs; a test
fails when a rule file gains a public function the kit does not pass. Each rule file owns one
concern:

| File in `rules/` | Concern |
|---|---|
| `tasks`, `prompt`, `harness` | the five stage tasks, the three review roles' tasks, the review's guardrails, the prompt of a run and the inline section of a local build run |
| `codemap` | the map of tracked files by folder a Spec or Build run is given |
| `command`, `commands`, `hooks`, `settings`, `telemetry` | command lines, Claude Code settings and hook JSON, telemetry variables |
| `srt`, `places` | srt settings of the setup, checks, preview, git and contained-process work; state and lock folders, domains, commit identity |
| `mounts` | the checks container's command line and its mounts |
| `permissions` | what a request would do and which the board's policy settles |
| `fence`, `inherited` | the owner's context fence and redaction, the text normal form every fence uses (a run's nonce names each fence's end line; ticket text is NFKC-normalised, stripped of format characters and neutralised before it is fenced); the variables a run inherits (an allowlist, in or out of the sandbox) |
| `logs`, `limits`, `spending`, `progress` | readers of a run log: usage, usage limit, price and budgets, progress |

## What the pipeline adds to a run

| Stage | Added | Where it is decided |
|---|---|---|
| Spec | the spec ends with a `## Blast radius` section (modules, files, interfaces, stored data, what could break); the code map and the same test patterns that Build uses | `rules/tasks.py`, `rules/codemap.py` |
| Build | waits in the queue until the requirements table names a check on every row and the spec's `## Blast radius` holds text, the reason shown as `spec not ready: ...`; a fix after a review does not wait; the code map; the run appends a `## Behaviour` section to `notes` (before and after, each row naming its test, then the changed files' coverage before and after where the project measures it), which opens the pull request's description with a line on the ticket's latest screen capture and its verdict, beside its capture of the same pages on the default branch (`code-factory shoot <repository> <ticket> --before`, taken while the board runs the default branch; it waits on no verdict) | `tickets/rules/documents.py` `build_gaps`, `follower/rules/queue.py` `spec_hold`, `delivery/rules/text.py` `behaviour_section` |
| Before Build | with `[agents] spec_reader = true`, a `read` run checks the requirements, spec and acceptance cases against each other before the first Build run, again after a Spec run rewrites them; with `plan_critic = true`, a `critique` run reads the Build's plan in `notes` once, after the first Build run ends. Each asks its objections as questions, which hold the ticket until answered; it is taken by an agent that did not write what it reads, with the review roles' read-only tools | `follower/rules/queue.py` `reader_due` |
| Review roles | each role of `[agents] review_roles` (`qa`, `security`, `tests`; another name is left out) runs as its own agent before the review, in the configured order, one at a time, taken by the review column's agents and never by the build's writer; a role is due until a run of it finishes after the latest Build run started. Its tools are read-only on the board (`whoami`, `get_ticket`, `list_activity`, `post_note`, `read_document`, `ask_question`, `list_questions`, `search_memory`, `get_checks`): it records findings as notes and writes no document | `REVIEW_ROLES`, `follower/rules/queue.py` `roles_due`, `platform/mcp/policy.py` `ROLE_STAGES` |
| Review | the roles that ran, whose notes it carries into the `review` document; then the guardrails `sensitive_paths` and `large_change`: crossing one the requirements do not ask for is a blocker, which returns the change to Build | `role_notes`, `guardrail_note` |

The board also files bug tickets by itself (`follower` step `file_failures`): one per breakage
of a default branch's own checks, named by the commit that broke it (else the last that passed),
and one per reverted merge in the Flow range, each with `caused_by` the ticket it came from.

The tasks and prompts name only tools of the run-build tool list (`tests/support/golden/mcp`); a test
compares them. The settings and hook output is checked against the golden files in
`tests/support/golden/agents`.

Only the runtimes `claude` and `codex` exist. The previous implementation's builders for omp, pi,
opencode and acp (`omp_settings`, `acp_settings`, `pi_files`, `acp_hosts`, `opencode_config`) and
the log readers of those runtimes are not ported; `process_settings` is the srt profile of a
contained codex process, and `connections.agent_refusal` decides which connection a runtime takes.

## Automatic repairs

A confirmed CI failure or merge conflict on the current ticket branch can queue a Build repair.
The `[agents] fix_rounds` setting defaults to 3 and limits these repairs over the ticket's lifetime.
Factory attempts each cause once per commit. If the agent cannot launch, the reservation is
released. When the cap is reached, the queue shows the reason and the owner can take over.
Review returns use the separate `review_rounds` setting.
