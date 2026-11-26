# Stages

`src/code_factory/stages` decides which column a ticket is in, says why a move is refused and
performs it, and reads the verdicts on a branch head (the board's checks, the fix loop, reviews).
The use cases are `StageService` (`service/`); every pure decision is in `rules/` and has no IO.

## What decides the column

`rules.derive_evidence` works five checklist items (spec, build, review, merged, released) from a
ticket's branch, the stored git facts (`stage_facts`), whether a pull request is recorded and
whether a published release names the ticket; `rules.stage_of` reads the column off them. A column
declared by hand (`stage_declarations`) wins. Reads never run git: the observer refreshes the facts
from `GitService.facts` (one read per repository) and the board's trees (`adapters/facts.py`);
`rules/gitfacts.py` answers for one ticket's branch. The diff reads of the review hold
(`adapters/git.py`) are this module's own.

| Gotcha | Behaviour |
|---|---|
| No facts row, or one read for another branch | judged by the ticket's own record: a declared branch counts as started, a recorded pull request as pushed; `facts_known` is false |
| A merge the ticket records | counts whatever git says (`ticket_facts`) |
| A local fast-forward | counts when the ticket branch tips are on the default line and a tip's recent commit subject starts with that ticket ID |
| A closed pull request | is not a review |
| Git unreadable in a pass | the old placement stays, `known` goes false, no presence change is appended |
| A drop on the column the evidence already reached, with nothing declared | declares nothing (the card keeps following its evidence) |
| A move that changes the effective column | also appends a `stage` record to the ticket's activity (read by the flow measures); the declaration and the record are two transactions, so making the same move again appends a record the first attempt lost |
| `released` | is what a release gives, never a column to move to |

The tickets module derives a column of its own (`Ticket.column`) from branch, pull request and
merge, with no declared column. The board uses stage assessments for placement, and the scheduler
uses landed evidence to resolve blockers, including archived blockers and PRs merged on GitHub.

Delivery runs the review and change-size rules against the shipped head before an automatic merge.
An owner hold is shown in the Inbox. The owner can resolve that hold by choosing Merge, with the
GitHub state and commit checks still required.

## Locks and records

`begin_fix_round`, `apply_review` and `observe` decide one ticket at a time under a transaction
advisory lock keyed on the ticket number (a row lock would lock nothing on a ticket with no row).
A round is unique per ticket, reason, head and review stamp (a review stamp that was given a round
on another head is `given`, as `round_given` reads it); a halt per ticket, head and reason.
An observation carries the time its git read began: a snapshot older than the stored one is
dropped, so a slow pass cannot overwrite a newer one. `apply_review` accepts only a review the run
itself submitted (`ReviewRecord.by` is the run's id or `run:<id>`) and, for the same run and head,
answers what it did the first time without writing.

## Background and bindings

The module's `background` hook starts `stage-observer`; its period is
`CODE_FACTORY_STAGE_OBSERVE_SECONDS` (default 30, never under 5). Reads of test files (`adapters/files.py`) do not cross a link with `**`, count files only and stop
at a deadline. The diff reads of the review hold start git from the trusted program
(`platform.programs`) with the repository variables removed.

`StageService.bind_log_reader`
is called by the checks module with a `ports.LogReader`: only that module knows which log names are
safe to open, so `checks_task` never opens a path a ledger record gives and quotes no log without it.

## Commands

`code-factory stage show CF-n | observe [CF-n ...] | rounds CF-n` (see `docs/reference/commands.md`).
